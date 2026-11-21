import { useEffect, useRef, useState } from 'react'
import { Camera, Check, ChevronDown, MapPin, QrCode, Search, Volume2 } from 'lucide-react'
import { api, ApiError } from '../data/api'
import type { Livability, Lookup, RoadListItem, Ward } from '../data/types'
import { inr, num, pct, date, shortWard } from '../lib/format'
import { ErrorBox, Id, Pending, Primary, Skel } from '../components/ui'
import { useAsync } from '../lib/useAsync'
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
            <BrowseRoads ward={ward} onOpenRoad={onOpenRoad} />
          </div>
        )}
      </div>

      <div className="kerb rounded-full" aria-hidden />

      <div className="grid items-stretch gap-6 lg:grid-cols-2">
        <YourArea ward={ward} w={w} loading={!wards} />
        <MovingHere ward={ward} onOpenRoad={onOpenRoad} />
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

type Check = { state: 'idle' } | { state: 'loading' } | { state: 'none'; name: string } | { state: 'error'; error: Error; name: string } | { state: 'ok'; data: Livability }

/** "Moving here?": flood hotspots, repair failures and hospital access within 1.5 km of a locality. */
function MovingHere({ ward, onOpenRoad }: { ward: string; onOpenRoad: (id: string) => void }) {
  const localities = useAsync(() => api.localities(), [])
  const [name, setName] = useState('')
  const [check, setCheck] = useState<Check>({ state: 'idle' })

  const run = async (n: string) => {
    setCheck({ state: 'loading' })
    try { setCheck({ state: 'ok', data: await api.livability(n) }) }
    catch (e) {
      if (e instanceof ApiError && e.status === 404) setCheck({ state: 'none', name: n })
      else setCheck({ state: 'error', error: e instanceof Error ? e : new Error(String(e)), name: n })
    }
  }

  // Start with the first locality in the selected ward, so the panel shows real numbers straight away.
  useEffect(() => {
    const first = localities.data?.find((l) => l.ward_code === ward)?.locality
    if (first) { setName(first); run(first) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [localities.data, ward])

  return (
    <div className="space-y-4 rounded-[20px] border border-hairline bg-surface p-3 sm:p-5">
      <h2 className="text-lg font-bold">Moving here? Check within 1.5 km</h2>
      <form onSubmit={(e) => { e.preventDefault(); if (name.trim()) run(name.trim()) }} className="flex flex-col gap-2 sm:flex-row">
        <label className="relative flex-1">
          <span className="sr-only">Locality</span>
          <MapPin size={18} strokeWidth={1.5} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
          <input value={name} onChange={(e) => setName(e.target.value)} list="localities" placeholder="Locality, e.g. Hindmata or हिंदमाता"
            className="min-h-[48px] w-full rounded-[8px] border border-hairline bg-concrete pl-10 pr-3 placeholder:text-muted focus:border-ink focus:outline-none" />
          <datalist id="localities">{localities.data?.map((l) => <option key={l.locality} value={l.locality}>{l.ward_code}</option>)}</datalist>
        </label>
        <button type="submit" disabled={!name.trim() || check.state === 'loading'}
          className="min-h-[48px] rounded-[8px] border border-ink bg-concrete px-5 text-sm font-semibold hover:bg-hwyellow/20 disabled:opacity-50">Check</button>
      </form>

      {localities.error && <ErrorBox error={localities.error} onRetry={localities.reload} />}
      {check.state === 'loading' && <div className="grid gap-3 sm:grid-cols-2">{[0, 1, 2, 3].map((i) => <Skel key={i} className="h-24" />)}</div>}
      {check.state === 'none' && <p className="rounded-[8px] border border-hairline bg-concrete p-4 text-sm">No locality called “{check.name}”. Pick one from the list.</p>}
      {check.state === 'error' && <ErrorBox error={check.error} onRetry={() => run(check.name)} />}
      {check.state === 'ok' && <LivabilityResult d={check.data} onOpenRoad={onOpenRoad} />}
    </div>
  )
}

function LivabilityResult({ d, onOpenRoad }: { d: Livability; onOpenRoad: (id: string) => void }) {
  const tiles: [string, string, string][] = [
    ['Flood hotspots', num(d.flood_hotspots_1500m), 'chronic waterlogging spots nearby'],
    ['Repairs that failed', d.failure_rate_30d_1500m === null ? 'None logged' : pct(d.failure_rate_30d_1500m), `reopened within 30 days, of ${num(d.jobs_1500m)} jobs`],
    ['Hospital access roads', num(d.hospital_access_roads_1500m), 'ambulance entry roads nearby'],
    ['Billed under warranty', d.ward_dlp_leakage_rate === null ? 'n/a' : pct(d.ward_dlp_leakage_rate, 1), `of ward ${d.ward_code} spend`],
  ]
  return (
    <div className="rise space-y-3">
      <p className="text-sm text-muted">Within {(d.radius_m / 1000).toFixed(1)} km of <span className="font-semibold text-ink">{d.locality}</span> (ward {d.ward_code})</p>
      <div className="grid gap-3 sm:grid-cols-2">
        {tiles.map(([label, value, note]) => (
          <div key={label} className="space-y-1 rounded-[8px] border border-hairline bg-concrete p-4">
            <p className="text-xs text-muted">{label}</p>
            <p className="text-2xl font-bold">{value}</p>
            <p className="text-xs text-muted">{note}</p>
          </div>
        ))}
      </div>
      {d.nearby_road_ids.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-muted">Nearest roads ({num(d.nearby_road_ids.length)}), open a receipt:</p>
          <div className="flex flex-wrap gap-2">
            {d.nearby_road_ids.slice(0, 8).map((id) => (
              <button key={id} onClick={() => onOpenRoad(id)} className="rounded-[6px] hover:opacity-80" aria-label={`Open road ${id}`}><Id>{id}</Id></button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

const PAGE = 20

/** Browse every road segment: filter by name or ID, optionally only the selected ward, 20 at a time. */
function BrowseRoads({ ward, onOpenRoad }: { ward: string; onOpenRoad: (id: string) => void }) {
  const [open, setOpen] = useState(false)
  const [filter, setFilter] = useState('')
  const [query, setQuery] = useState('')
  const [onlyWard, setOnlyWard] = useState(true)
  const [rows, setRows] = useState<RoadListItem[]>([])
  const [more, setMore] = useState(false)
  const [state, setState] = useState<{ loading: boolean; error: Error | null }>({ loading: false, error: null })

  useEffect(() => { const t = window.setTimeout(() => setQuery(filter.trim()), 300); return () => window.clearTimeout(t) }, [filter])

  const load = async (offset: number) => {
    setState({ loading: true, error: null })
    try {
      const page = await api.roads({ q: query || undefined, ward: onlyWard ? ward : undefined, limit: PAGE, offset })
      setRows((r) => (offset === 0 ? page : [...r, ...page]))
      setMore(page.length === PAGE)
      setState({ loading: false, error: null })
    } catch (e) { setState({ loading: false, error: e instanceof Error ? e : new Error(String(e)) }) }
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (open) load(0) }, [open, query, onlyWard, ward])

  return (
    <div className="rounded-[8px] border border-hairline bg-concrete">
      <button onClick={() => setOpen((o) => !o)} aria-expanded={open}
        className="flex min-h-[48px] w-full items-center justify-between gap-3 px-4 text-sm font-semibold hover:bg-hwyellow/20">
        Browse all roads <ChevronDown size={18} strokeWidth={1.5} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="space-y-3 border-t border-hairline bg-surface p-3">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <label className="relative flex-1">
              <span className="sr-only">Filter roads by name or ID</span>
              <Search size={16} strokeWidth={1.5} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
              <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter by road name or ID, e.g. SV Road or RD0048"
                className="min-h-[44px] w-full rounded-[8px] border border-hairline bg-concrete pl-9 pr-3 text-sm placeholder:text-muted focus:border-ink focus:outline-none" />
            </label>
            <label className="flex min-h-[44px] items-center gap-2 text-sm">
              <input type="checkbox" checked={onlyWard} onChange={(e) => setOnlyWard(e.target.checked)} className="h-4 w-4 accent-ink" />
              Only ward {ward}
            </label>
          </div>

          {state.error && <ErrorBox error={state.error} onRetry={() => load(0)} />}
          {state.loading && rows.length === 0 && <div className="space-y-2">{[0, 1, 2, 3].map((i) => <Skel key={i} className="h-14" />)}</div>}
          {!state.loading && !state.error && rows.length === 0 && (
            <p className="p-2 text-sm text-muted">No roads match{query ? ` “${query}”` : ''}{onlyWard ? ` in ward ${ward}` : ''}.</p>
          )}

          {rows.length > 0 && (
            <ul className="divide-y divide-hairline rounded-[8px] border border-hairline">
              {rows.map((r) => (
                <li key={r.road_id}>
                  <button onClick={() => onOpenRoad(r.road_id)} className="flex w-full flex-wrap items-center justify-between gap-x-4 gap-y-1 px-3 py-3 text-left hover:bg-hwyellow/10">
                    <span className="min-w-0">
                      <span className="block font-semibold">{r.road_name}{r.segment_no ? <span className="font-normal text-muted"> · segment {r.segment_no}</span> : null}</span>
                      <span className="flex flex-wrap items-center gap-2 text-xs text-muted">
                        <Id>{r.road_id}</Id> ward {r.ward_code}
                        {r.under_dlp && <span className="rounded-[6px] bg-hwgreen px-1.5 py-0.5 font-semibold text-white">Under warranty</span>}
                      </span>
                    </span>
                    <span className="text-right text-xs text-muted">
                      <span className="block text-sm font-semibold text-ink">{inr(r.total_billed_inr)} billed</span>
                      {r.flagged_bills_count > 0 ? `${inr(r.rupees_at_stake)} at stake · ${num(r.flagged_bills_count)} flagged` : 'No flagged bills'}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {more && (
            <button onClick={() => load(rows.length)} disabled={state.loading}
              className="min-h-[44px] w-full rounded-[8px] border border-ink bg-concrete text-sm font-semibold hover:bg-hwyellow/20 disabled:opacity-50">
              {state.loading ? 'Loading…' : 'Show more roads'}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
