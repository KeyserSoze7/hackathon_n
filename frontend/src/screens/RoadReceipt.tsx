import { useMemo, useState } from 'react'
import { FileText, ShieldCheck, ShieldOff, CircleAlert } from 'lucide-react'
import { api } from '../data/api'
import { useAsync } from '../lib/useAsync'
import { inr, num, date, DETECTOR, cleanName } from '../lib/format'
import { ErrorBox, Id, Modal, Pending, Primary, Skel } from '../components/ui'
import type { Flag, RoadDetail, TimelineEvent } from '../data/types'

export default function RoadReceipt({ roadId, onFind }: { roadId: string; onFind: () => void }) {
  const { data, loading, error, reload } = useAsync(() => Promise.all([api.road(roadId), api.timeline(roadId)]), [roadId])
  const [notice, setNotice] = useState(false)
  const [showAll, setShowAll] = useState(false)

  if (error) return <ErrorBox error={error} onRetry={reload} />
  if (loading || !data) return <Loading />
  const [road, timeline] = data
  const shown = showAll ? timeline : timeline.slice(0, 10)
  const failed = road.work_orders.filter((w) => w.reopened_within_30d)
  const firstComplaint = timeline.find((e) => e.event_type === 'complaint')
  const firstFlag = road.flags[0]
  const flaggedWo = firstFlag ? road.work_orders.find((w) => w.work_order_id === firstFlag.work_order_id) : undefined

  return (
    <div className="rise mx-auto max-w-3xl space-y-6">
      <div className="flex overflow-hidden rounded-[16px] border border-hairline bg-surface">
        <div className="w-2.5 shrink-0 bg-hwyellow" aria-hidden />
        <div className="flex flex-1 flex-col justify-between gap-4 p-5 sm:flex-row sm:items-center">
          <div className="min-w-0 space-y-1">
            <p className="mono font-semibold text-hwgreen">{road.road_id} · WARD {road.ward_code} · {road.surface.toUpperCase()}</p>
            <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{road.road_name}</h1>
            <p className="flex items-center gap-2 text-sm text-muted">
              {road.under_dlp ? <ShieldCheck size={16} strokeWidth={1.5} className="text-hwgreen" /> : <ShieldOff size={16} strokeWidth={1.5} />}
              {road.under_dlp ? 'Under warranty' : 'Out of warranty'}. Resurfaced {date(road.last_resurfaced)}.
            </p>
          </div>
          <button onClick={onFind} className="min-h-[42px] shrink-0 rounded-[8px] border border-hairline bg-concrete px-4 text-sm font-semibold hover:border-ink">Find another road</button>
        </div>
      </div>

      <div className="space-y-6 rounded-[20px] border border-hairline bg-surface p-3 sm:p-6">
        <div className="grid gap-4 rounded-[8px] border border-hairline bg-concrete p-5 md:grid-cols-2">
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted">Billed to BMC this monsoon</p>
            <p className="text-[40px] font-bold leading-none tracking-tight sm:text-[44px]">{inr(road.total_billed_inr)}</p>
            <p className="text-xs text-muted">{num(road.work_orders_count)} repair jobs</p>
          </div>
          <div className="space-y-1 border-hairline md:border-l md:pl-5">
            <p className="text-xs font-medium text-muted">Rupees at stake in flagged bills</p>
            <p className="text-[40px] font-bold leading-none tracking-tight text-hwgreen sm:text-[44px]">{inr(road.rupees_at_stake)}</p>
            <p className="text-xs text-muted">{num(road.flagged_bills_count)} bills need explanation</p>
          </div>
        </div>

        <div className="space-y-4">
          <h2 className="text-base font-bold">Connected proof trail</h2>
          <div className="centerline ml-3 space-y-6 py-1 pl-7">
            <Step dot="ring"
              meta={firstComplaint ? `${firstComplaint.ref_id} · ${date(firstComplaint.event_at)} · ${firstComplaint.detail.channel ?? ''}` : 'No complaint linked'}
              title={firstComplaint ? 'Citizen complaint logged' : 'No complaint on this road'}
              desc={firstComplaint ? `${firstComplaint.detail.description ?? ''}` : 'Repairs on this road have no linked complaint.'} />
            <Step dot="solid"
              meta={flaggedWo ? `${flaggedWo.work_order_id} · ${inr(flaggedWo.cost_inr)} · ${cleanName(flaggedWo.contractor_name)}` : `${num(road.work_orders_count)} repair jobs`}
              title={flaggedWo ? `Repair billed: ${flaggedWo.repair_method}` : 'Repairs billed'}
              desc={firstFlag ? firstFlag.rule_text : 'No flagged bill on this road.'} />
            <div className="relative">
              <span className="absolute -left-[37px] top-3 h-4 w-4 rounded-[3px] border border-ink bg-hwyellow" aria-hidden />
              <div className="space-y-1 rounded-[8px] border-2 border-ink p-4">
                <p className="mono font-bold">{num(failed.length)} OF {num(road.work_orders_count)} REPAIRS</p>
                <h3 className="text-base font-bold">{failed.length ? `${num(failed.length)} repairs failed within 30 days` : 'No repair failed within 30 days'}</h3>
                {failed[0] && <p className="text-sm">First failure: <Id>{failed[0].work_order_id}</Id> by {cleanName(failed[0].contractor_name)}.</p>}
              </div>
            </div>
            <Step dot="yellow" meta={`${num(road.flags.length)} flags`} title="Audit flags" desc="Each flag is a rule the data triggered, not a finding of wrongdoing. The contractor or ward engineer can reply on the record." />
          </div>
        </div>

        <FlagList road={road} onReplied={reload} />

        <Primary onClick={() => setNotice(true)} className="w-full !min-h-[54px] text-base">
          <FileText size={20} strokeWidth={1.5} /> Draft defect notice (EN / मराठी)
        </Primary>
      </div>

      <section className="rounded-[20px] border border-hairline bg-surface p-3 sm:p-6">
        <h2 className="text-lg font-bold">What happened, in order</h2>
        <p className="mt-1 text-sm text-muted">{num(timeline.filter((e) => e.event_type === 'complaint').length)} complaints, {num(road.work_orders_count)} repairs, {num(timeline.filter((e) => e.event_type === 'accident').length)} accidents.</p>
        <ol className="mt-5 border-l border-hairline">
          {shown.map((e) => <TimelineRow key={`${e.event_type}-${e.ref_id}-${e.event_at}`} e={e} road={road} />)}
        </ol>
        {timeline.length > shown.length && (
          <button onClick={() => setShowAll(true)} className="mt-2 text-sm font-semibold underline decoration-hwyellow decoration-2 underline-offset-4">Show remaining {num(timeline.length - shown.length)} events</button>
        )}
      </section>

      {notice && (
        <Modal title={`Defect notice: ${road.road_name}`} onClose={() => setNotice(false)}>
          <Pending label="Notice drafting in English and Marathi" />
        </Modal>
      )}
    </div>
  )
}

function Step({ dot, meta, title, desc }: { dot: 'ring' | 'solid' | 'yellow'; meta: string; title: string; desc: string }) {
  const cls = dot === 'ring' ? 'border-2 border-ink bg-surface' : dot === 'solid' ? 'bg-ink' : 'border-2 border-ink bg-hwyellow'
  return (
    <div className="relative space-y-1">
      <span className={`absolute -left-[37px] top-1 h-4 w-4 rounded-full ${cls}`} aria-hidden />
      <p className="mono text-muted">{meta}</p>
      <h3 className="text-base font-bold">{title}</h3>
      <p className="text-sm text-muted">{desc}</p>
    </div>
  )
}

function FlagList({ road, onReplied }: { road: RoadDetail; onReplied: () => void }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="space-y-3">
      <button onClick={() => setOpen(!open)} aria-expanded={open}
        className="flex min-h-[46px] w-full items-center justify-between rounded-[8px] border border-hairline bg-concrete px-4 text-sm font-semibold hover:border-ink">
        <span>{open ? 'Hide evidence rows' : `Show evidence rows (${num(road.flags.length)})`}</span>
        <span aria-hidden className={`transition-transform ${open ? 'rotate-180' : ''}`}>▾</span>
      </button>
      {open && (
        <div className="rise space-y-4">
          <ul className="divide-y divide-hairline rounded-[8px] border border-hairline bg-concrete">
            {road.flags.map((f) => <FlagRow key={f.flag_id} f={f} />)}
          </ul>
          <ReplyForm flags={road.flags} onReplied={onReplied} />
        </div>
      )}
    </div>
  )
}

function FlagRow({ f }: { f: Flag }) {
  return (
    <li className="space-y-2 p-4 text-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <p className="flex items-center gap-2 font-semibold"><CircleAlert size={16} strokeWidth={1.5} className="shrink-0" />{DETECTOR[f.detector] ?? f.detector} · tier {f.tier} · {f.status_label}</p>
          <p className="text-muted">{f.rule_text}</p>
          <p className="flex flex-wrap gap-1.5 pt-1">{f.evidence_row_ids.map((e) => <Id key={e}>{e}</Id>)}</p>
        </div>
        <p className="shrink-0 font-semibold">{inr(f.rupees_at_stake)}</p>
      </div>
      {f.replies.map((r, i) => (
        <p key={i} className="rounded-[8px] border border-hairline bg-surface p-3">
          <span className="font-semibold">{(r.author_role ?? 'reply').replace('_', ' ')}{r.author_name ? ` · ${r.author_name}` : ''}:</span> {r.body}
        </p>
      ))}
    </li>
  )
}

function ReplyForm({ flags, onReplied }: { flags: Flag[]; onReplied: () => void }) {
  const [flagId, setFlagId] = useState(flags[0]?.flag_id ?? '')
  const [role, setRole] = useState<'ward_engineer' | 'contractor' | 'other'>('ward_engineer')
  const [name, setName] = useState('')
  const [body, setBody] = useState('')
  const [state, setState] = useState<'idle' | 'sending' | 'done' | 'error'>('idle')
  const ok = useMemo(() => flagId && body.trim().length > 0, [flagId, body])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!ok) return
    setState('sending')
    try {
      await api.reply(flagId, { author_role: role, author_name: name.trim() || undefined, body: body.trim() })
      setBody(''); setState('done'); onReplied()
    } catch { setState('error') }
  }
  if (!flags.length) return null
  return (
    <form onSubmit={submit} className="space-y-3">
      <p className="text-sm font-semibold">Right of reply (ward engineer or contractor)</p>
      <div className="grid gap-2 sm:grid-cols-3">
        <label className="text-xs text-muted">Flag
          <select value={flagId} onChange={(e) => setFlagId(e.target.value)} className="mt-1 min-h-[42px] w-full rounded-[8px] border border-hairline bg-surface px-2 text-sm text-ink">
            {flags.map((f) => <option key={f.flag_id} value={f.flag_id}>{f.work_order_id} · {DETECTOR[f.detector] ?? f.detector}</option>)}
          </select>
        </label>
        <label className="text-xs text-muted">Replying as
          <select value={role} onChange={(e) => setRole(e.target.value as typeof role)} className="mt-1 min-h-[42px] w-full rounded-[8px] border border-hairline bg-surface px-2 text-sm text-ink">
            <option value="ward_engineer">Ward engineer</option><option value="contractor">Contractor</option><option value="other">Other</option>
          </select>
        </label>
        <label className="text-xs text-muted">Name (optional)
          <input value={name} onChange={(e) => setName(e.target.value)} maxLength={120} className="mt-1 min-h-[42px] w-full rounded-[8px] border border-hairline bg-surface px-3 text-sm text-ink" />
        </label>
      </div>
      <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={3} maxLength={4000} placeholder="For example, utility trench permit or site note"
        className="w-full rounded-[8px] border border-hairline bg-surface p-3 text-sm placeholder:text-muted focus:border-ink focus:outline-none" />
      <div className="flex items-center gap-3">
        <button type="submit" disabled={!ok || state === 'sending'} className="min-h-[46px] rounded-[8px] bg-ink px-4 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-40">
          {state === 'sending' ? 'Saving…' : 'Log reply'}
        </button>
        {state === 'done' && <span className="rise text-sm">Reply saved on the record.</span>}
        {state === 'error' && <span className="text-sm">The reply could not be saved. Try again.</span>}
      </div>
    </form>
  )
}

function TimelineRow({ e, road }: { e: TimelineEvent; road: RoadDetail }) {
  const wo = road.work_orders.find((w) => w.work_order_id === e.ref_id)
  let title = ''
  let note = ''
  if (e.event_type === 'complaint') { title = `Complaint: ${String(e.detail.status ?? '')}`; note = String(e.detail.description ?? '') }
  else if (e.event_type === 'work_order_assigned') { title = `Repair assigned: ${e.detail.repair_method} · ${inr(Number(e.detail.cost_inr))}`; note = wo ? cleanName(wo.contractor_name) : String(e.detail.contractor_id ?? '') }
  else if (e.event_type === 'work_order_completed') {
    title = `Repair completed${e.detail.reopened_within_30d ? ': failed within 30 days' : ''}`
    note = `${e.detail.sla_met ? 'Within SLA' : 'After SLA'}${e.detail.rain_mm_on_completion_day != null ? ` · ${e.detail.rain_mm_on_completion_day} mm rain that day` : ''}`
  } else { title = `${e.detail.severity} accident`; note = String(e.detail.probable_cause ?? '') }
  return (
    <li className="relative pb-5 pl-6">
      <span className={`absolute -left-[5px] top-1.5 h-2.5 w-2.5 rounded-full ${e.event_type === 'accident' ? 'bg-ink' : e.detail.reopened_within_30d ? 'bg-hwyellow ring-2 ring-ink' : 'bg-hairline'}`} aria-hidden />
      <div className="flex flex-wrap items-baseline gap-x-3">
        <span className="mono text-muted">{date(e.event_at)}</span>
        <span className="font-medium">{title}</span>
      </div>
      <div className="mt-0.5 flex flex-wrap items-center gap-2 text-sm text-muted"><Id>{e.ref_id}</Id>{note && <span>{note}</span>}</div>
    </li>
  )
}

function Loading() {
  return (
    <div className="mx-auto max-w-3xl space-y-6" role="status" aria-label="Loading road receipt">
      <Skel className="h-28" /><Skel className="h-40" /><Skel className="h-56" />
    </div>
  )
}
