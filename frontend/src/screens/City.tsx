import { useState } from 'react'
import { api } from '../data/api'
import { useAsync } from '../lib/useAsync'
import type { Ward } from '../data/types'
import { inr, num, pct, date, DETECTOR, shortWard, cleanName } from '../lib/format'
import { ErrorBox, Id, Primary, Skel } from '../components/ui'
import WardMap from '../components/WardMap'

export default function City({ wards, ward, onWard, onOpenRoad }: { wards: Ward[] | null; ward: string; onWard: (c: string) => void; onOpenRoad: (id: string) => void }) {
  const city = useAsync(api.city, [])
  const [sel, setSel] = useState<string | null>(null)
  const queue = useAsync(() => api.queue(sel ?? undefined, 8), [sel])

  if (city.error) return <ErrorBox error={city.error} onRetry={city.reload} />
  const c = city.data
  const selected = wards?.find((w) => w.ward_code === (sel ?? ''))

  return (
    <div className="rise space-y-8">
      <div className="max-w-4xl">
        {c ? (
          <h1 className="text-2xl font-bold leading-tight tracking-tight sm:text-3xl">
            {inr(c.total_spend_inr)} of monsoon repairs went out{wards ? ` across ${wards.length} wards` : ''}. {inr(c.recoverable_dlp_inr)} of it was billed on roads under warranty.
          </h1>
        ) : <Skel className="h-20 w-full" />}
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card loading={!c} title="Monsoon spend against budget">
          {c && <><p className="text-3xl font-bold tracking-tight">{inr(c.total_spend_inr)}</p><p className="text-xs text-muted">{pct(c.total_spend_inr / c.total_budget_inr, 1)} of the {inr(c.total_budget_inr)} ward budget</p></>}
        </Card>
        <Card loading={!c} title="Billed on roads under warranty" strong>
          {c && <><p className="text-3xl font-bold tracking-tight text-hwgreen">{inr(c.recoverable_dlp_inr)}</p><p className="text-xs text-muted">{num(c.flags_by_detector.DLP_PAID_TWICE ?? 0)} bills flagged as recoverable under the warranty rule</p></>}
        </Card>
        <Card loading={!c} title="Bills needing explanation">
          {c && <>
            <p className="text-3xl font-bold tracking-tight">{num(c.flagged_bills_count)}</p>
            <p className="text-xs text-muted">{Object.entries(c.flags_by_detector).map(([k, v]) => `${num(v)} ${(DETECTOR[k] ?? k).toLowerCase()}`).join(' · ')}</p>
          </>}
        </Card>
      </div>

      <div className="space-y-5 rounded-[20px] border border-hairline bg-surface p-5 sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-bold">Ward map: share of jobs billed under warranty</h2>
            <p className="text-sm text-muted">Select a ward to filter the table. Dashed wards are flood-prone with few complaints per resident.</p>
          </div>
          <button onClick={() => setSel(null)} aria-pressed={sel === null}
            className={`min-h-[42px] rounded-[8px] px-4 text-sm ${sel === null ? 'bg-hwyellow font-bold' : 'border border-hairline bg-concrete font-medium hover:border-ink'}`}>All wards</button>
        </div>
        <div className="grid gap-8 lg:grid-cols-[1.3fr_1fr]">
          {wards ? <WardMap wards={wards} selected={sel} onSelect={(c) => { setSel(c); if (c) onWard(c) }} /> : <Skel className="h-[420px]" />}
          <div>
            {selected ? (
              <dl className="rise grid grid-cols-2 gap-x-6 gap-y-4 text-sm">
                <h3 className="col-span-2 text-lg font-bold">Ward {selected.ward_code} · {shortWard(selected.ward_name)}</h3>
                <Stat label="Spent" value={inr(selected.spend_inr)} sub={`of ${inr(selected.budget_inr)}`} />
                <Stat label="Billed under warranty" value={inr(selected.recoverable_dlp_inr)} sub={`${pct(selected.dlp_leakage_rate, 1)} of jobs`} />
                <Stat label="Bills flagged" value={num(selected.flagged_bills_count)} />
                <Stat label="Complaints per lakh" value={selected.complaints_per_lakh.toFixed(1)} sub={selected.under_reported_flag ? 'Few complaints for the risk' : undefined} />
                <Stat label="Flood hotspots" value={num(selected.flood_hotspots_count)} />
                <Stat label="Accidents" value={num(selected.accidents_count)} />
              </dl>
            ) : <p className="text-sm text-muted">Select a ward on the map to see its figures. Current ward in the header: {ward}.</p>}
          </div>
        </div>
      </div>

      <div className="space-y-4 rounded-[20px] border border-hairline bg-surface p-5 sm:p-6">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-lg font-bold">{sel ? `Flagged bills in ward ${sel}` : 'Flagged bills with the most rupees at stake'}</h2>
          <span className="mono text-muted">{queue.data ? `${queue.data.length} ROWS` : ''}</span>
        </div>
        {queue.error ? <ErrorBox error={queue.error} onRetry={queue.reload} /> : (
          <div className="relative overflow-x-auto">
            <table className="w-full min-w-[640px] border-collapse text-left">
              <thead>
                <tr className="border-b border-hairline text-xs text-muted">
                  <th scope="col" className="pb-3 pr-4 font-medium">Road and work order</th>
                  <th scope="col" className="px-3 pb-3 font-medium">Ward</th>
                  <th scope="col" className="px-3 pb-3 font-medium">Flag</th>
                  <th scope="col" className="px-3 pb-3 text-right font-medium">Rupees at stake</th>
                  <th scope="col" className="pb-3 pl-3 text-right font-medium"><span className="sr-only">Action</span></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline text-sm">
                {queue.loading || !queue.data ? [0, 1, 2, 3].map((i) => <tr key={i}><td colSpan={5} className="py-3"><Skel className="h-10" /></td></tr>)
                  : queue.data.length === 0 ? <tr><td colSpan={5} className="py-6 text-center text-muted">No flagged bills in this ward.</td></tr>
                  : queue.data.map((q) => (
                    <tr key={q.work_order_id} className="hover:bg-concrete">
                      <td className="py-4 pr-4"><p className="font-bold">{q.road_name}</p><p className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted"><Id>{q.road_id}</Id><Id>{q.work_order_id}</Id><span>{cleanName(q.contractor_name)} · {date(q.completed_at)}</span></p></td>
                      <td className="mono px-3 py-4">{q.ward_code}</td>
                      <td className="px-3 py-4"><p>{q.detectors.map((d) => DETECTOR[d] ?? d).join(', ')}</p><p className="text-xs text-muted">{q.status_label}</p></td>
                      <td className="px-3 py-4 text-right font-bold">{inr(q.rupees_at_stake)}</td>
                      <td className="py-4 pl-3 text-right"><Primary onClick={() => onOpenRoad(q.road_id)} className="!min-h-[40px] !px-3.5 text-xs">Open receipt</Primary></td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

function Card({ title, strong, loading, children }: { title: string; strong?: boolean; loading: boolean; children: React.ReactNode }) {
  return (
    <div className={`space-y-1 rounded-[16px] bg-surface p-5 ${strong ? 'border-2 border-ink' : 'border border-hairline'}`}>
      <p className="text-xs font-medium text-muted">{title}</p>
      {loading ? <><Skel className="h-9 w-40" /><Skel className="h-3 w-56" /></> : children}
    </div>
  )
}
function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return <div><dt className="text-muted">{label}</dt><dd className="text-lg font-semibold">{value}{sub && <span className="block text-xs font-normal text-muted">{sub}</span>}</dd></div>
}
