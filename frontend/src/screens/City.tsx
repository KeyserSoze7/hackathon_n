import { useState } from 'react'
import { api, notYet } from '../data/api'
import { useAsync } from '../lib/useAsync'
import type { Ward } from '../data/types'
import { inr, num, pct, date, DETECTOR, shortWard, cleanName } from '../lib/format'
import { ErrorBox, Id, Pending, Primary, Skel } from '../components/ui'
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

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
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
        <Card loading={!c} title="Repairs that failed within 30 days">
          {c && c.reopened_within_30d_count != null && c.work_orders_count ? <>
            <p className="text-3xl font-bold tracking-tight">{num(c.reopened_within_30d_count)}</p>
            <p className="text-xs text-muted">{pct(c.reopened_within_30d_count / c.work_orders_count)} of {num(c.work_orders_count)} jobs{c.sla_met_rate != null ? ` · ${pct(c.sla_met_rate)} met their SLA` : ''}</p>
          </> : <p className="text-sm text-muted">Data coming in</p>}
        </Card>
      </div>

      {c?.recoverable_dlp_rule && (
        <div className="rounded-[12px] border border-hairline bg-surface p-4 text-sm text-muted">
          <span className="font-semibold text-ink">How the warranty figure is counted.</span> {c.recoverable_dlp_rule}
          {c.dlp_road_spend_inr != null && <> All spend on roads still under warranty is {inr(c.dlp_road_spend_inr)}; only the part above is recoverable.</>}
        </div>
      )}

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
            {selected ? (<div className="space-y-4">
              <dl className="rise grid grid-cols-2 gap-x-6 gap-y-4 text-sm">
                <h3 className="col-span-2 text-lg font-bold">Ward {selected.ward_code} · {shortWard(selected.ward_name)}</h3>
                <Stat label="Spent" value={inr(selected.spend_inr)} sub={`of ${inr(selected.budget_inr)}`} />
                <Stat label="Billed under warranty" value={inr(selected.recoverable_dlp_inr)} sub={`${pct(selected.dlp_leakage_rate, 1)} of jobs`} />
                <Stat label="Bills flagged" value={num(selected.flagged_bills_count)} />
                <Stat label="Complaints per lakh" value={selected.complaints_per_lakh.toFixed(1)} sub={selected.under_reported_flag ? 'Few complaints for the risk' : undefined} />
                <Stat label="Flood hotspots" value={num(selected.flood_hotspots_count)} />
                <Stat label="Accidents" value={num(selected.accidents_count)} />
              </dl>
              <WardTrail ward={selected.ward_code} />
            </div>) : <p className="text-sm text-muted">Select a ward on the map to see its figures. Current ward in the header: {ward}.</p>}
          </div>
        </div>
      </div>

      <div className="space-y-4 rounded-[20px] border border-hairline bg-surface p-5 sm:p-6">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-lg font-bold">{sel ? `Flagged bills in ward ${sel}` : 'Flagged bills with the most rupees at stake'}</h2>
          <span className="mono text-muted">{queue.data ? `${queue.data.length} ROWS` : ''}</span>
        </div>
        {queue.error ? <ErrorBox error={queue.error} onRetry={queue.reload} /> : queue.loading || !queue.data ? (
          <div className="grid gap-3 md:grid-cols-2">{[0, 1, 2, 3].map((i) => <Skel key={i} className="h-44" />)}</div>
        ) : queue.data.length === 0 ? <p className="text-sm text-muted">No flagged bills in this ward.</p> : (
          <div className="grid gap-3 md:grid-cols-2">
            {queue.data.map((q) => (
              <article key={q.work_order_id} className="flex flex-col justify-between gap-4 rounded-[16px] border border-hairline bg-concrete p-4">
                <div className="space-y-2">
                  <div className="flex items-start justify-between gap-3">
                    <h3 className="font-bold leading-snug">{q.road_name}</h3>
                    <p className="shrink-0 text-xl font-bold">{inr(q.rupees_at_stake)}</p>
                  </div>
                  <p className="text-sm">{q.detectors.map((d) => DETECTOR[d] ?? d).join(', ')}</p>
                  <p className="text-xs text-muted">{q.status_label} · Ward {q.ward_code} · {cleanName(q.contractor_name)} · {date(q.completed_at)}</p>
                  <p className="flex flex-wrap gap-1.5"><Id>{q.road_id}</Id><Id>{q.work_order_id}</Id></p>
                </div>
                <Primary onClick={() => onOpenRoad(q.road_id)} className="w-full !min-h-[44px] text-sm">Open receipt</Primary>
              </article>
            ))}
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

/** Ward money trail: where this ward's monsoon money went, by contractor, and how much went on fixes that failed within 30 days. */
function WardTrail({ ward }: { ward: string }) {
  const t = useAsync(() => api.moneyTrail(ward).catch((e) => { if (notYet(e)) return null; throw e }), [ward])
  if (t.loading) return <Skel className="h-40" />
  if (t.error) return <ErrorBox error={t.error} onRetry={t.reload} />
  if (!t.data) return <Pending label="Money trail by contractor and failed fixes for this ward" />
  const d = t.data
  return (
    <div className="space-y-3 rounded-[16px] border border-hairline bg-concrete p-4">
      <p className="font-bold">Where ward {ward}'s money went</p>
      {d.summary && <p className="text-sm">{d.summary}</p>}
      <div className="rounded-[12px] border-2 border-ink bg-surface p-3"><p className="text-xs text-muted">Spent on fixes that failed within 30 days</p><p className="text-xl font-bold">{inr(d.failed_within_30d.spend_inr)} <span className="text-sm font-normal text-muted">· {num(d.failed_within_30d.jobs)} jobs</span></p></div>
      <div className="grid gap-2">
        {d.by_contractor.map((c) => (
          <div key={c.contractor_id} className="rounded-[12px] border border-hairline bg-surface p-3 text-sm">
            <div className="flex items-start justify-between gap-2"><p className="font-semibold">{cleanName(c.contractor_name)}</p><p className="font-bold">{inr(c.spend_inr)}</p></div>
            <p className="text-xs text-muted">{num(c.jobs)} jobs · {num(c.failed_30d)} failed within 30 days ({inr(c.failed_spend_inr)})</p>
          </div>
        ))}
      </div>
    </div>
  )
}
