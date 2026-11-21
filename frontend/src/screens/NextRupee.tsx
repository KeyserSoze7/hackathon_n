import { useEffect, useMemo, useState } from 'react'
import { ArrowRight } from 'lucide-react'
import { api } from '../data/api'
import { useAsync } from '../lib/useAsync'
import type { Allocation, Ward } from '../data/types'
import { inr, num, pct, shortWard, REASON } from '../lib/format'
import { ErrorBox, Id, Skel } from '../components/ui'

const STEP = 100000

export default function NextRupee({ wards, ward, onWard, onOpenRoad }: { wards: Ward[] | null; ward: string; onWard: (c: string) => void; onOpenRoad: (id: string) => void }) {
  const allocWards = useAsync(api.allocWards, [])
  const items = useAsync(() => api.nextRupee(ward), [ward])
  const w = allocWards.data?.find((x) => x.ward_code === ward)

  const [budget, setBudget] = useState<number | null>(null)
  const [alloc, setAlloc] = useState<Allocation | null>(null)
  const [busy, setBusy] = useState(false)
  const [allocErr, setAllocErr] = useState<Error | null>(null)

  // Start from the backend's recommended budget whenever the ward changes.
  useEffect(() => { setAlloc(null); if (w) setBudget(w.recommended_budget_inr) }, [ward, w?.ward_code])

  // Exact re-solve on the server, debounced while the slider moves.
  useEffect(() => {
    if (budget === null) return
    let live = true
    setBusy(true)
    const t = window.setTimeout(() => {
      api.allocate(ward, budget).then((a) => { if (live) { setAlloc(a); setAllocErr(null); setBusy(false) } }, (e) => { if (live) { setAllocErr(e); setBusy(false) } })
    }, 300)
    return () => { live = false; window.clearTimeout(t) }
  }, [ward, budget])

  const max = useMemo(() => (w ? Math.max(2000000, Math.ceil((w.recommended_budget_inr * 4) / STEP) * STEP) : 2000000), [w])
  const roadOf = useMemo(() => Object.fromEntries((items.data ?? []).map((i) => [i.item_id, i.road_id])), [items.data])
  const fundedIds = useMemo(() => new Set(alloc?.funded.map((f) => f.item_id) ?? []), [alloc])
  const waiting = (items.data ?? []).filter((i) => i.bucket !== 'A_OWED_BY_CONTRACTOR_DLP' && !fundedIds.has(i.item_id))
  const freed = alloc?.bucket_a_dlp.reduce((a, i) => a + i.estimated_repair_cost_inr, 0) ?? 0

  if (allocWards.error) return <ErrorBox error={allocWards.error} onRetry={allocWards.reload} />
  if (items.error) return <ErrorBox error={items.error} onRetry={items.reload} />

  return (
    <div className="rise space-y-8">
      <div className="max-w-3xl space-y-2">
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Where the next rupee does the most good</h1>
        <p className="text-muted">Items are ranked by harm avoided per rupee. Roads under warranty cost BMC nothing, so budget goes to the rest. Planning is per ward.</p>
      </div>

      <div className="space-y-5 rounded-[20px] border border-hairline bg-surface p-6 sm:p-7">
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
          <div className="space-y-3">
            <label className="block text-sm">
              <span className="font-medium text-muted">Ward</span>
              <select value={ward} onChange={(e) => onWard(e.target.value)} className="mt-1.5 block min-h-[42px] w-full min-w-[220px] rounded-[8px] border border-hairline bg-surface px-3">
                {(wards ?? []).map((x) => <option key={x.ward_code} value={x.ward_code}>{x.ward_code} · {shortWard(x.ward_name)}</option>)}
              </select>
            </label>
            <div>
              <p className="text-sm text-muted">Budget to spend</p>
              <p className="text-4xl font-bold tracking-tight sm:text-5xl">{budget === null ? '…' : inr(budget)}</p>
            </div>
          </div>
          <div className="sm:text-right">
            <p className="text-sm text-muted">Funded by this budget</p>
            <p className="text-xl font-bold text-hwgreen">{alloc ? `${num(alloc.funded.length)} items · ${inr(alloc.spend_inr)}` : '…'}</p>
            <p className="text-sm text-muted">{alloc ? `Harm avoided ${alloc.harm_avoided.toFixed(1)}` : ''}</p>
          </div>
        </div>
        <div className="space-y-2">
          <input type="range" className="slider" min={0} max={max} step={STEP} value={budget ?? 0} onChange={(e) => setBudget(+e.target.value)} aria-label="Budget to spend, in rupees" disabled={budget === null} />
          <div className="flex justify-between text-xs text-muted"><span>₹0</span><span>{inr(max)}</span></div>
        </div>
        {w && (
          <p className="text-sm text-muted">
            Backend recommendation for this ward: {inr(w.recommended_budget_inr)} (equity floor {inr(w.equity_floor_inr)}). Budget {inr(w.budget_2025_inr)}, spent {inr(w.spend_2025_inr)}, remaining {inr(w.remaining_2025_inr)}.
          </p>
        )}
      </div>

      {allocErr && <ErrorBox error={allocErr} />}

      <div className="grid items-start gap-6 lg:grid-cols-12">
        <div className="space-y-5 rounded-[20px] border-2 border-hwyellow bg-surface p-5 sm:p-6 lg:col-span-5">
          <div className="space-y-1">
            <p className="text-sm font-bold text-hwgreen">{alloc ? `${inr(freed)} freed across ${num(alloc.bucket_a_dlp.length)} items under warranty` : 'Loading…'}</p>
            <h2 className="text-lg font-bold">Costs BMC ₹0: the contractor owes these repairs</h2>
          </div>
          {!alloc ? <Skel className="h-24" /> : alloc.bucket_a_dlp.length === 0 ? <p className="text-sm text-muted">No warranty items in this ward.</p> : (
            <ol className="space-y-3">
              {alloc.bucket_a_dlp.map((a) => (
                <li key={a.item_id} className="space-y-1 rounded-[8px] border border-hairline bg-concrete p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0"><p className="text-sm font-bold">{a.road_name}</p><p className="text-xs text-muted">{a.issue}</p></div>
                    <div className="shrink-0 text-right"><p className="font-bold text-hwgreen">₹0</p><p className="text-xs text-muted line-through">{inr(a.estimated_repair_cost_inr)}</p></div>
                  </div>
                  <p className="text-xs text-muted">{a.explanation}</p>
                </li>
              ))}
            </ol>
          )}
        </div>

        <div className="space-y-5 rounded-[20px] border border-hairline bg-surface p-5 sm:p-6 lg:col-span-7">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-lg font-bold">Ranked items to fund next</h2>
            <span className={`mono font-semibold transition-opacity ${busy ? 'opacity-40' : ''}`}>{alloc && budget !== null ? `USED ${inr(alloc.spend_inr)} OF ${inr(budget)}` : ''}</span>
          </div>
          {!alloc || items.loading ? <div className="space-y-3">{[0, 1, 2].map((i) => <Skel key={i} className="h-20" />)}</div> : (
            <ol className={`space-y-3 transition-opacity ${busy ? 'opacity-60' : ''}`}>
              {alloc.funded.length === 0 && <li className="text-sm text-muted">Raise the budget to fund the first item.</li>}
              {alloc.funded.map((f, i) => (
                <Row key={f.item_id} n={i + 1} funded name={f.road_name} issue={f.issue} method={f.method} cost={f.cost} reasons={f.reason_codes} road={roadOf[f.item_id]} onOpen={onOpenRoad} />
              ))}
              {waiting.map((i) => (
                <Row key={i.item_id} funded={false} name={i.road_name} issue={i.issue} method={i.recommended_method} cost={i.estimated_repair_cost_inr} reasons={i.reason_codes} road={i.road_id} onOpen={onOpenRoad} />
              ))}
            </ol>
          )}
        </div>
      </div>
    </div>
  )
}

function Row({ n, funded, name, issue, method, cost, reasons, road, onOpen }: {
  n?: number; funded: boolean; name: string; issue: string; method: string; cost: number; reasons: string[]; road?: string; onOpen: (id: string) => void
}) {
  return (
    <li className={`rounded-[8px] p-4 ${funded ? 'border border-ink bg-concrete' : 'border border-hairline bg-surface opacity-55'}`}>
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
        <div className="min-w-0 space-y-1">
          <p className="text-sm font-bold">{n ? `${n}. ` : ''}{name}</p>
          <p className="flex flex-wrap items-center gap-2 text-xs text-muted">{road && <Id>{road}</Id>}<span>{issue} · {method}</span></p>
          <p className="text-xs text-muted">{reasons.map((r) => REASON[r] ?? r).join(' · ')}</p>
        </div>
        <div className="flex shrink-0 items-center gap-3 sm:flex-col sm:items-end sm:gap-1">
          <p className="font-bold">{inr(cost)}</p>
          <p className={`mono font-bold ${funded ? 'text-hwgreen' : 'text-muted'}`}>{funded ? 'FUNDED' : 'NEXT CYCLE'}</p>
          {road && <button onClick={() => onOpen(road)} className="flex items-center gap-1 text-xs font-semibold underline decoration-hwyellow decoration-2 underline-offset-4">Receipt <ArrowRight size={12} strokeWidth={1.5} /></button>}
        </div>
      </div>
    </li>
  )
}
