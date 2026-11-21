import { useEffect, useMemo, useState } from 'react'
import type { Ward } from '../data/types'
import { pct, shortWard } from '../lib/format'

type Geo = { features: { properties: { ward_code: string }; geometry: { coordinates: number[][][] } }[] }

// Sequential single-hue ramp. Value = dlp_leakage_rate (share of ward jobs billed under warranty).
const RAMP = ['#fdf3d0', '#f8dd8b', '#f5b700', '#c98600', '#8f5b00', '#4d3200']
const bucket = (v: number, max: number) => Math.min(RAMP.length - 1, Math.floor((v / (max || 1)) * RAMP.length))

export default function WardMap({ wards, selected, onSelect }: { wards: Ward[]; selected: string | null; onSelect: (c: string | null) => void }) {
  const [geo, setGeo] = useState<Geo | null>(null)
  const [hover, setHover] = useState<string | null>(null)
  useEffect(() => { fetch('/wards.geojson').then((r) => r.json()).then(setGeo) }, [])

  const byCode = useMemo(() => Object.fromEntries(wards.map((w) => [w.ward_code, w])), [wards])
  const max = Math.max(...wards.map((w) => w.dlp_leakage_rate))

  const { paths, vw, vh } = useMemo(() => {
    if (!geo) return { paths: [], vw: 100, vh: 100 }
    const pts = geo.features.flatMap((f) => f.geometry.coordinates[0])
    const lons = pts.map((p) => p[0]), lats = pts.map((p) => p[1])
    const minLon = Math.min(...lons), maxLon = Math.max(...lons), minLat = Math.min(...lats), maxLat = Math.max(...lats)
    const k = Math.cos(((minLat + maxLat) / 2) * Math.PI / 180)
    const W = (maxLon - minLon) * k, H = maxLat - minLat, S = 100 / Math.max(W, H)
    const proj = ([lo, la]: number[]) => [(lo - minLon) * k * S, (maxLat - la) * S]
    const paths = geo.features.map((f) => {
      const ring = f.geometry.coordinates[0].map(proj)
      return {
        code: f.properties.ward_code,
        d: 'M' + ring.map((p) => `${p[0].toFixed(2)},${p[1].toFixed(2)}`).join('L') + 'Z',
        cx: ring.reduce((a, p) => a + p[0], 0) / ring.length, cy: ring.reduce((a, p) => a + p[1], 0) / ring.length,
      }
    })
    return { paths, vw: W * S, vh: H * S }
  }, [geo])

  if (!geo) return <div className="skeleton h-[420px] w-full" role="status" aria-label="Loading map" />
  const active = hover ?? selected
  const w = active ? byCode[active] : null

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${vw.toFixed(1)} ${vh.toFixed(1)}`} className="mx-auto max-h-[600px] w-full" role="img" aria-label="Mumbai wards shaded by share of jobs billed under warranty">
        {paths.map((p) => {
          const ward = byCode[p.code]
          const isSel = selected === p.code
          const dashed = ward?.under_reported_flag && !isSel
          return (
            <path key={p.code} d={p.d} fill={ward ? RAMP[bucket(ward.dlp_leakage_rate, max)] : '#eee'}
              stroke={isSel || dashed ? '#111317' : '#ffffff'} strokeWidth={isSel ? 0.9 : dashed ? 0.5 : 0.35}
              strokeDasharray={dashed ? '1.2 0.9' : undefined} strokeLinejoin="round"
              className="cursor-pointer transition-[stroke-width] duration-150 hover:stroke-ink"
              onMouseEnter={() => setHover(p.code)} onMouseLeave={() => setHover(null)}
              onClick={() => onSelect(isSel ? null : p.code)} tabIndex={0}
              onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && onSelect(isSel ? null : p.code)}
              aria-label={`Ward ${p.code}`} />
          )
        })}
        {paths.map((p) => (
          <text key={p.code} x={p.cx} y={p.cy} fontSize="2.3" textAnchor="middle" dominantBaseline="central" fontWeight="600"
            className="pointer-events-none select-none"
            fill={byCode[p.code] && bucket(byCode[p.code].dlp_leakage_rate, max) >= 3 ? '#fff' : '#111317'}>{p.code}</text>
        ))}
      </svg>
      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
        <span>Less</span>
        <span className="flex overflow-hidden rounded-sm">{RAMP.map((c) => <i key={c} className="h-2.5 w-6" style={{ background: c }} />)}</span>
        <span>More jobs billed under warranty</span>
        <span className="ml-3 inline-block h-3 w-5 border border-dashed border-ink" aria-hidden />
        <span>Flood-prone, few complaints</span>
      </div>
      {w && (
        <div className="pointer-events-none absolute right-0 top-0 rounded-[8px] bg-ink px-3 py-2 text-sm text-white">
          <div className="font-semibold">Ward {w.ward_code} · {shortWard(w.ward_name)}</div>
          <div className="text-white/80">{pct(w.dlp_leakage_rate, 1)} of jobs billed under warranty</div>
        </div>
      )}
    </div>
  )
}
