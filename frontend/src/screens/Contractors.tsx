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

      <div className="grid items-start gap-6 lg:grid-cols-12">
        <div className="space-y-5 rounded-[20px] border border-hairline bg-surface p-5 sm:p-6 lg:col-span-8">
          {loading || !data ? <div className="space-y-4" role="status" aria-label="Loading contractors">{[0, 1, 2, 3].map((i) => <Skel key={i} className="h-24" />)}</div> : (
            <div className="relative overflow-x-auto">
              <table className="w-full min-w-[720px] border-collapse text-left">
                <thead>
                  <tr className="border-b border-hairline text-xs text-muted">
                    <th scope="col" className="pb-3 pr-3 font-medium">Contractor</th>
                    <th scope="col" className="px-2 pb-3 text-right font-medium">Failed within 30 days</th>
                    <th scope="col" className="px-2 pb-3 text-right font-medium">Met SLA</th>
                    <th scope="col" className="border-l border-hairline pb-3 pl-4 font-medium">Where they worked</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-hairline text-sm">
                  {[...data].sort((a, b) => b.total_billed_inr - a.total_billed_inr).map((c) => <Row key={c.contractor_id} c={c} />)}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <aside className="space-y-4 rounded-[20px] border border-hairline bg-surface p-5 sm:p-6 lg:col-span-4">
          <h2 className="text-lg font-bold">How to read this</h2>
          <ul className="space-y-3 text-sm text-muted">
            <li><span className="font-semibold text-ink">Expected rate</span> is what would be expected given the rain, tides, roads and repair methods in this contractor's jobs.</li>
            <li><span className="font-semibold text-ink">Verdict</span> compares the observed rate with the expected one. The 90% range shows how sure the comparison is.</li>
            <li><span className="font-semibold text-ink">Drivers</span> list the factors that moved the expected rate up or down.</li>
            <li>There are no grades. The figures are for review and do not establish fault.</li>
          </ul>
        </aside>
      </div>
    </div>
  )
}

function Row({ c }: { c: Contractor }) {
  const ci = c.durability_ratio_ci90
  return (
    <tr className="align-top">
      <td className="py-4 pr-3">
        <p className="font-bold">{cleanName(c.contractor_name)}</p>
        <p className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted"><Id>{c.contractor_id}</Id><span>{num(c.jobs_count)} jobs · {inr(c.total_billed_inr)}</span></p>
        <details className="mt-2 text-xs text-muted">
          <summary className="cursor-pointer font-semibold text-ink underline decoration-hwyellow decoration-2 underline-offset-4">Why this verdict</summary>
          <p className="mt-2">{c.explanation}</p>
          {c.drivers.length > 0 && <ul className="mt-2 list-disc space-y-1 pl-4">{c.drivers.map((d) => <li key={d.feature}>{d.plain}</li>)}</ul>}
          {c.evidence_reopened_wo_ids.length > 0 && <p className="mt-2 flex flex-wrap items-center gap-1.5">Failed repairs: {c.evidence_reopened_wo_ids.slice(0, 6).map((id) => <Id key={id}>{id}</Id>)}{c.evidence_reopened_wo_ids.length > 6 ? ` and ${c.evidence_reopened_wo_ids.length - 6} more` : ''}</p>}
        </details>
      </td>
      <td className="px-2 py-4 text-right">
        <p className="text-lg font-bold">{pct(c.reopen_rate_30d, 1)}</p>
        <p className="text-xs text-muted">Expected {pct(c.expected_reopen_rate_30d, 1)}</p>
        <p className="text-xs font-semibold capitalize">{c.durability_verdict}</p>
        {ci.length === 2 && <p className="text-xs text-muted">Ratio {c.durability_ratio_obs_over_exp.toFixed(2)} ({ci[0].toFixed(2)}–{ci[1].toFixed(2)})</p>}
      </td>
      <td className="px-2 py-4 text-right">
        <p className="text-lg font-bold">{pct(c.sla_met_rate, 1)}</p>
        <p className="text-xs text-muted">Expected {pct(c.expected_sla_met_rate, 1)}</p>
        <p className="text-xs font-semibold capitalize">{c.speed_verdict}</p>
        <p className="text-xs text-muted">Median bill {c.cost_vs_rate_median.toFixed(2)}× rate card</p>
      </td>
      <td className="space-y-0.5 border-l border-hairline py-4 pl-4 text-xs">
        <p>{pct(c.context.flood_prone_share)} of jobs in flood-prone wards</p>
        <p>{c.context.avg_rain_next7_mm.toFixed(0)} mm average rain in the 7 days after a job (city {c.context.city_avg_rain_next7_mm.toFixed(0)} mm)</p>
        <p>{c.context.avg_big_tides_next7.toFixed(1)} big tides in those 7 days</p>
        <p>{num(c.context.avg_peak_vehicles)} average peak-hour vehicles</p>
      </td>
    </tr>
  )
}
