import { api } from '../data/api'
import { useAsync } from '../lib/useAsync'
import { inr, num, pct, cleanName } from '../lib/format'
import { ErrorBox, Id, Skel } from '../components/ui'
import type { Contractor } from '../data/types'

export default function Contractors() {
  const { data, loading, error, reload } = useAsync(api.contractors, [])
  if (error) return <ErrorBox error={error} onRetry={reload} />

  return (
    <div className="rise space-y-6">
      <div className="max-w-3xl space-y-2">
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Each contractor's record, shown beside the rain and flooding they worked in</h1>
        <p className="text-muted">Raw failure rates punish contractors who work in flood-prone wards. Each rate here sits beside what is expected for that contractor's own roads, rain and tides.</p>
      </div>

      <div className="rounded-[12px] border border-hairline bg-surface p-4 text-sm text-muted">
        <span className="font-semibold text-ink">How to read this.</span> Expected is what the rain, tides, roads and repair methods of a contractor's jobs would predict. The verdict compares the actual rate to it. There are no grades; the figures are for review and do not establish fault.
      </div>

      {loading || !data ? (
        <div className="grid gap-4 md:grid-cols-2" role="status" aria-label="Loading contractors">{[0, 1, 2, 3].map((i) => <Skel key={i} className="h-72" />)}</div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {[...data].sort((a, b) => b.total_billed_inr - a.total_billed_inr).map((c) => <ContractorCard key={c.contractor_id} c={c} />)}
        </div>
      )}
    </div>
  )
}

function ContractorCard({ c }: { c: Contractor }) {
  const ci = c.durability_ratio_ci90
  return (
    <article className="space-y-4 rounded-[20px] border border-hairline bg-surface p-4 sm:p-5">
      <header>
        <h2 className="text-lg font-bold leading-snug">{cleanName(c.contractor_name)}</h2>
        <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted"><Id>{c.contractor_id}</Id><span>{num(c.jobs_count)} jobs · {inr(c.total_billed_inr)}</span></p>
      </header>

      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-[12px] border border-hairline bg-concrete p-3">
          <p className="text-xs text-muted">Failed within 30 days</p>
          <p className="text-2xl font-bold">{pct(c.reopen_rate_30d, 1)}</p>
          <p className="text-xs text-muted">Expected {pct(c.expected_reopen_rate_30d, 1)}</p>
          <p className="mt-1 text-xs font-semibold capitalize">{c.durability_verdict}</p>
          {ci.length === 2 && <p className="text-xs text-muted">Ratio {c.durability_ratio_obs_over_exp.toFixed(2)} ({ci[0].toFixed(2)}–{ci[1].toFixed(2)})</p>}
        </div>
        <div className="rounded-[12px] border border-hairline bg-concrete p-3">
          <p className="text-xs text-muted">Met the SLA</p>
          <p className="text-2xl font-bold">{pct(c.sla_met_rate, 1)}</p>
          <p className="text-xs text-muted">Expected {pct(c.expected_sla_met_rate, 1)}</p>
          <p className="mt-1 text-xs font-semibold capitalize">{c.speed_verdict}</p>
          <p className="text-xs text-muted">Median bill {c.cost_vs_rate_median.toFixed(2)}× rate card</p>
        </div>
      </div>

      <div className="space-y-1 rounded-[12px] border border-hairline p-3 text-sm">
        <p className="text-xs font-semibold text-muted">Where they worked</p>
        <p>{pct(c.context.flood_prone_share)} of jobs in flood-prone wards</p>
        <p>{c.context.avg_rain_next7_mm.toFixed(0)} mm rain in the week after a job (city {c.context.city_avg_rain_next7_mm.toFixed(0)} mm)</p>
        <p>{c.context.avg_big_tides_next7.toFixed(1)} big tides in that week</p>
        <p>{num(c.context.avg_peak_vehicles)} peak-hour vehicles on average</p>
      </div>

      <details className="rounded-[12px] border border-hairline p-3 text-sm">
        <summary className="cursor-pointer font-semibold underline decoration-hwyellow decoration-2 underline-offset-4">Why this verdict</summary>
        <p className="mt-3 text-muted">{c.explanation}</p>
        {c.drivers.length > 0 && (
          <div className="mt-3 grid gap-2">{c.drivers.map((d) => <p key={d.feature} className="rounded-[8px] bg-concrete p-2 text-muted">{d.plain}</p>)}</div>
        )}
        {c.evidence_reopened_wo_ids.length > 0 && (
          <p className="mt-3 flex flex-wrap items-center gap-1.5 text-muted">Failed repairs: {c.evidence_reopened_wo_ids.slice(0, 6).map((id) => <Id key={id}>{id}</Id>)}{c.evidence_reopened_wo_ids.length > 6 ? ` and ${c.evidence_reopened_wo_ids.length - 6} more` : ''}</p>
        )}
      </details>
    </article>
  )
}
