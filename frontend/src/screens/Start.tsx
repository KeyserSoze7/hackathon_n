import { useEffect, useRef, useState } from 'react'
import { Camera, Check, QrCode, Search, Volume2 } from 'lucide-react'
import { api } from '../data/api'
import type { Lookup, Ward } from '../data/types'
import { inr, num, pct, date, shortWard } from '../lib/format'
import { Id, Pending, Primary, Skel } from '../components/ui'
import ReportFlow from '../components/ReportFlow'

type Tab = 'signboard' | 'qr' | 'search'
type Found = { state: 'idle' } | { state: 'loading' } | { state: 'none'; text: string } | { state: 'ok'; data: Lookup; text: string; answer?: string }

export default function Start({ wards, ward, onOpenRoad }: { wards: Ward[] | null; ward: string; onOpenRoad: (id: string) => void }) {
  const [tab, setTab] = useState<Tab>('signboard')
  const [text, setText] = useState('')
  const [found, setFound] = useState<Found>({ state: 'idle' })
  const w = wards?.find((x) => x.ward_code === ward)
  const [reporting, setReporting] = useState<Lookup | null>(null)

  // Typed questions go to the Claude citizen query (plain-language answer + matched road); fall back to the plain lookup.
  const find = async (q: string, ask = false) => {
    setFound({ state: 'loading' })
    if (ask) {
      try {
        const r = await api.citizenQuery(q)
        if (r.lookup) return setFound({ state: 'ok', data: r.lookup, text: q, answer: r.plain_language_reply })
      } catch { /* fall back to lookup */ }
    }
    try { setFound({ state: 'ok', data: await api.lookup(q), text: q }) }
    catch { setFound({ state: 'none', text: q }) }
  }

  const TABS: [Tab, string][] = [['signboard', 'Photo of signboard'], ['qr', 'Scan QR code'], ['search', 'Type road or area']]

  return (
    <div className="rise space-y-8">
      <div className="max-w-3xl space-y-2">
        <h1 className="text-2xl font-bold leading-tight tracking-tight sm:text-4xl">Find any Mumbai road and see what it cost, whether it is under warranty, and how it has held up</h1>
        <p className="text-muted">Type a road name or a landmark. Every answer links back to the work orders, complaints and flags behind it.</p>
      </div>

      <div className="space-y-5 rounded-[20px] border border-hairline bg-surface p-3 sm:p-5">
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
          <h2 className="text-lg font-bold">Find a road</h2>
          <div role="tablist" aria-label="How to find a road" className="grid grid-cols-3 gap-1 rounded-[12px] border border-hairline bg-concrete p-[4px]">
            {TABS.map(([id, label]) => (
              <button key={id} role="tab" aria-selected={tab === id} onClick={() => { setTab(id); setFound({ state: 'idle' }) }}
                className={`min-h-[42px] rounded-[8px] px-3 text-xs sm:text-sm ${tab === id ? 'bg-hwyellow font-semibold' : 'font-medium text-muted hover:text-ink'}`}>{label}</button>
            ))}
          </div>
        </div>

        {tab === 'signboard' && (
          <div className="grid items-stretch gap-5 lg:grid-cols-12">
            <div className="relative flex min-h-[230px] flex-col items-center justify-center overflow-hidden rounded-[8px] border-2 border-dashed border-hairline bg-concrete p-6 lg:col-span-7">
              {found.state === 'loading' && <div className="scan" />}
              <div className="w-full max-w-sm overflow-hidden rounded-[8px] border-2 border-ink bg-surface">
                <div className="flex items-center justify-between bg-hwgreen px-4 py-2 text-white"><span className="mono font-semibold tracking-wider">BMC ROAD</span></div>
                <div className="px-4 py-4 text-center"><p className="text-xl font-bold tracking-tight">KURLA ANDHERI ROAD</p></div>
                <div className="kerb" />
              </div>
              <p className="mt-4 text-center text-xs text-muted">Sample board. The board text is sent to the road lookup. Reading a real photo is not connected yet.</p>
            </div>
            <div className="flex flex-col justify-between gap-4 lg:col-span-5">
              <Result found={found} onOpenRoad={onOpenRoad} onReport={setReporting} />
              <Primary onClick={() => find('Kurla Andheri Road')} disabled={found.state === 'loading'} className="w-full !min-h-[54px] text-base">
                <Camera size={20} strokeWidth={1.5} /> Photograph road signboard
              </Primary>
            </div>
          </div>
        )}

        {tab === 'qr' && (
          <div className="grid items-center gap-5 lg:grid-cols-12">
            <div className="flex min-h-[200px] items-center justify-center rounded-[8px] border border-hairline bg-concrete lg:col-span-5">
              <QrCode size={96} strokeWidth={1.5} />
            </div>
            <div className="space-y-3 lg:col-span-7">
              <h3 className="text-lg font-bold">Scan a road's QR code</h3>
              <Pending label="QR codes on signboards" />
            </div>
          </div>
        )}

        {tab === 'search' && (
          <div className="space-y-4">
            <form onSubmit={(e) => { e.preventDefault(); if (text.trim()) find(text.trim(), true) }} className="flex flex-col gap-2 sm:flex-row">
              <label className="relative flex-1">
                <span className="sr-only">Road name or landmark</span>
                <Search size={18} strokeWidth={1.5} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
                <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Andheri subway ke bahar khadda wapas aa gaya, paisa kahan gaya?"
                  className="min-h-[52px] w-full rounded-[8px] border border-hairline bg-concrete pl-10 pr-3 placeholder:text-muted focus:border-ink focus:outline-none" />
              </label>
              <Primary type="submit" disabled={!text.trim() || found.state === 'loading'}>Ask</Primary>
            </form>
            <Result found={found} onOpenRoad={onOpenRoad} onReport={setReporting} />
            <Pending label="Browse all roads" />
          </div>
        )}
      </div>

      <div className="kerb rounded-full" aria-hidden />

      <div className="grid items-stretch gap-6 lg:grid-cols-2">
        <YourArea ward={ward} w={w} loading={!wards} />
        <div className="space-y-4 rounded-[20px] border border-hairline bg-surface p-3 sm:p-5">
          <h2 className="text-lg font-bold">Moving here? Check within 1.5 km</h2>
          <Pending label="Flood hotspots, repair failures and hospital access near a locality" />
        </div>
      </div>

      {reporting && (
        <ReportFlow road={{ road_id: reporting.matched_road_id, road_name: reporting.road.road_name, ward_code: reporting.ward_code }}
          locality={reporting.matched_locality} onClose={() => setReporting(null)} onOpenRoad={onOpenRoad} />
      )}
    </div>
  )
}

function Result({ found, onOpenRoad, onReport }: { found: Found; onOpenRoad: (id: string) => void; onReport: (d: Lookup) => void }) {
  if (found.state === 'idle') return <div className="rounded-[12px] border border-hairline bg-concrete p-5 text-sm text-muted">Results appear here.</div>
  if (found.state === 'loading') return (
    <div className="space-y-3 rounded-[12px] border border-hairline bg-concrete p-5" role="status" aria-label="Looking up road">
      <Skel className="h-4 w-1/3" /><Skel className="h-6 w-3/4" /><Skel className="h-10 w-full" />
    </div>
  )
  if (found.state === 'none') return <div className="rounded-[12px] border border-hairline bg-concrete p-5 text-sm">No road matched “{found.text}”. Try a road name or a known locality.</div>

  const { data: d } = found
  const under = d.warranty_status === 'UNDER_DLP'
  return (
    <div className="rise space-y-4 rounded-[12px] border-2 border-ink bg-surface p-5">
      {found.answer && (
        <div className="rounded-[12px] border border-hairline bg-hwyellow/20 p-4">
          <p className="text-xs font-semibold text-muted">Answer, written by Claude from the records below</p>
          <p className="mt-1 text-[15px] leading-relaxed">{found.answer}</p>
        </div>
      )}
      <p className="text-xs font-semibold text-hwgreen">
        Matched by {d.matched_via.replace('_', ' ')}: “{d.matched_text}”{d.matched_locality ? ` · ${d.matched_locality}` : ''}
      </p>
      <h3 className="text-lg font-bold">{d.road.road_name}</h3>
      <p className="flex flex-wrap items-center gap-2 text-sm text-muted"><Id>{d.matched_road_id}</Id> <span>Ward {d.ward_code}</span> <span>{num(d.road_distance_m)} m from match</span></p>
      <dl className="grid grid-cols-2 gap-2 text-sm">
        <div className="rounded-[8px] bg-concrete p-3"><dt className="text-xs text-muted">Warranty</dt><dd className="font-semibold">{under ? 'Under warranty' : 'Out of warranty'}</dd></div>
        <div className="rounded-[8px] bg-concrete p-3"><dt className="text-xs text-muted">Billed this monsoon</dt><dd className="font-semibold">{inr(d.road.total_billed_inr)}</dd></div>
        <div className="rounded-[8px] bg-concrete p-3"><dt className="text-xs text-muted">Flagged bills</dt><dd className="font-semibold">{num(d.road.flagged_bills_count)}</dd></div>
        <div className="rounded-[8px] bg-concrete p-3"><dt className="text-xs text-muted">Resurfaced</dt><dd className="font-semibold">{date(d.road.last_resurfaced)}</dd></div>
      </dl>
      <Primary onClick={() => onOpenRoad(d.matched_road_id)} className="w-full">Open road receipt</Primary>
      <button onClick={() => onReport(d)} className="flex min-h-[48px] w-full items-center justify-center rounded-[8px] border border-ink bg-surface font-semibold hover:bg-hwyellow/20">Report a problem on this road</button>
    </div>
  )
}

function YourArea({ ward, w, loading }: { ward: string; w?: Ward; loading: boolean }) {
  const [playing, setPlaying] = useState(false)
  const [progress, setProgress] = useState(0)
  const timer = useRef<number | undefined>(undefined)
  const stop = () => { window.clearInterval(timer.current); setPlaying(false); setProgress(0); try { window.speechSynthesis?.cancel() } catch { /* unsupported */ } }
  useEffect(() => stop, [])
  useEffect(() => { stop() }, [ward])

  const play = () => {
    if (!w) return
    if (playing) return stop()
    try {
      const u = new SpeechSynthesisUtterance(`Ward ${w.ward_code}, ${shortWard(w.ward_name)}. Spent ${inr(w.spend_inr)} of ${inr(w.budget_inr)}. Billed under warranty ${inr(w.recoverable_dlp_inr)}. ${w.flagged_bills_count} bills need explanation.`)
      u.lang = 'en-IN'; window.speechSynthesis.speak(u)
    } catch { /* unsupported */ }
    setPlaying(true); setProgress(0)
    timer.current = window.setInterval(() => setProgress((p) => { if (p >= 100) { stop(); return 0 } return p + 1 }), 100)
  }

  return (
    <div className="flex flex-col justify-between gap-5 rounded-[20px] border border-hairline bg-surface p-3 sm:p-5">
      <div className="space-y-4">
        <div className="flex items-baseline justify-between gap-2">
          <h2 className="text-lg font-bold">Your area</h2>
          <span className="mono font-semibold text-hwgreen">{w ? `WARD ${w.ward_code} · ${shortWard(w.ward_name).toUpperCase()}` : `WARD ${ward}`}</span>
        </div>
        {loading || !w ? (
          <div className="grid gap-3 sm:grid-cols-3">{[0, 1, 2].map((i) => <Skel key={i} className="h-24" />)}</div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="space-y-1 rounded-[8px] border border-hairline bg-concrete p-4">
              <p className="text-xs text-muted">Spent this monsoon</p>
              <p className="text-2xl font-bold">{inr(w.spend_inr)}</p>
              <p className="text-xs text-muted">of {inr(w.budget_inr)} budget</p>
            </div>
            <div className="space-y-1 rounded-[8px] border border-ink bg-concrete p-4">
              <p className="text-xs text-muted">Billed under warranty</p>
              <p className="text-2xl font-bold">{inr(w.recoverable_dlp_inr)}</p>
              <p className="text-xs text-muted">{pct(w.dlp_leakage_rate, 1)} of jobs · {num(w.flagged_bills_count)} bills flagged</p>
            </div>
            <div className="space-y-1 rounded-[8px] border border-hairline bg-concrete p-4">
              <p className="text-xs text-muted">Complaints per lakh people</p>
              <p className="text-2xl font-bold">{w.complaints_per_lakh.toFixed(1)}</p>
              <p className="text-xs text-muted">{w.under_reported_flag ? 'Flood-prone, few complaints' : `${num(w.flood_hotspots_count)} flood hotspots`}</p>
            </div>
          </div>
        )}
      </div>
      <div className="space-y-2">
        <button onClick={play} disabled={!w} className="flex min-h-[52px] w-full items-center justify-between gap-3 rounded-[8px] border border-ink bg-concrete px-4 text-sm font-semibold hover:bg-hwyellow/20 disabled:opacity-50">
          <span className="flex items-center gap-3"><Volume2 size={20} strokeWidth={1.5} />{playing ? 'Playing…' : 'Listen to a 10-second summary'}</span>
          {playing && <span className="flex h-4 items-end gap-0.5">{[0, 0.15, 0.3].map((d) => <span key={d} className="eq h-full w-1 rounded-full bg-ink" style={{ animationDelay: `${d}s` }} />)}</span>}
        </button>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-concrete"><div className="h-full bg-hwyellow transition-all duration-100" style={{ width: `${progress}%` }} /></div>
      </div>
    </div>
  )
}
