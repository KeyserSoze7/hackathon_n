import { Check } from 'lucide-react'
import type { CitizenReport } from '../data/types'
import { date } from '../lib/format'

// Report lifecycle labels (see decision.md). Officers move a report forward; the citizen sees each step.
export const STATUS_LABEL: Record<string, string> = {
  reported: 'Report received',
  matched_to_contract: 'Matched to the road and its contract',
  under_review: 'An officer is reviewing it',
  payment_held: 'Payment on the matched bill held',
  contractor_notified: 'Contractor notified',
  repair_scheduled: 'Repair scheduled',
  resolved: 'Marked fixed',
  rejected: 'Closed',
}
export const statusLabel = (s: string) => STATUS_LABEL[s] ?? s.replace(/_/g, ' ')

/** Shows the event history when the backend sends `events`, otherwise the step list in `tracker`. */
export default function Tracker({ report }: { report: CitizenReport }) {
  if (report.events?.length) {
    return (
      <div className="grid gap-2">
        {report.events.map((e, i) => {
          const last = i === report.events!.length - 1
          return (
            <div key={`${e.status}-${e.at}`} className={`flex gap-3 rounded-[12px] border p-3 ${last ? 'border-ink bg-hwyellow/25' : 'border-ink bg-surface'}`}>
              <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full border-2 border-ink bg-hwyellow"><Check size={14} strokeWidth={2} /></span>
              <span className="min-w-0">
                <span className="block text-sm font-semibold">{statusLabel(e.status)}</span>
                <span className="text-xs text-muted">{date(e.at)}{e.by_role ? ` · ${e.by_role.replace(/_/g, ' ')}` : ''}</span>
                {e.note && <span className="mt-1 block text-sm">{e.note}</span>}
              </span>
            </div>
          )
        })}
        {report.rejection_reason && <p className="text-sm">Reason: {report.rejection_reason}</p>}
      </div>
    )
  }
  return (
    <div className="grid gap-2">
      {report.tracker.map((t, i) => {
        const current = t.status ? t.status === 'current' : !t.done && report.tracker.slice(0, i).every((x) => x.done)
        return (
          <div key={t.step} className={`flex items-center gap-3 rounded-[12px] border p-3 ${t.done ? 'border-ink bg-surface' : current ? 'border-dashed border-ink bg-concrete' : 'border-hairline bg-concrete text-muted'}`}>
            <span className={`grid h-7 w-7 shrink-0 place-items-center rounded-full border-2 ${t.done ? 'border-ink bg-hwyellow' : 'border-hairline'}`}>{t.done ? <Check size={14} strokeWidth={2} /> : <span className="text-xs">{i + 1}</span>}</span>
            <span className="min-w-0"><span className="block text-sm font-semibold">{t.label ?? statusLabel(t.step)}</span><span className="text-xs text-muted">{t.done ? `Done${t.at ? ` · ${date(t.at)}` : ''}` : current ? 'In progress' : 'Waiting'}</span></span>
          </div>
        )
      })}
    </div>
  )
}
