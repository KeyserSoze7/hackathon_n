import { useState } from 'react'
import { LogOut, Search } from 'lucide-react'
import { adminSession, api, notYet } from '../data/api'
import { DEMO } from '../data/demo'
import { useAsync } from '../lib/useAsync'
import { cleanName, date, DETECTOR, inr, num, shortWard } from '../lib/format'
import type { AdminSession, CitizenReport, QueueItem, Ward } from '../data/types'
import { ErrorBox, Id, Modal, Pending, Primary, Skel } from '../components/ui'
import Tracker, { statusLabel } from '../components/Tracker'

// Ward office dashboard (#admin, not in the public nav). Officers move reports through the lifecycle the citizen sees.
// Endpoints that the backend has not shipped yet render "Data coming in"; working endpoints (report lookup, flags, replies) are live.

const NEXT: Record<string, string[]> = {
  reported: ['under_review', 'rejected'],
  matched_to_contract: ['under_review', 'rejected'],
  under_review: ['payment_held', 'contractor_notified', 'rejected'],
  payment_held: ['contractor_notified'],
  contractor_notified: ['repair_scheduled', 'resolved'],
  repair_scheduled: ['resolved'],
  resolved: [], rejected: [],
}
const input = 'mt-1.5 min-h-[48px] w-full rounded-[8px] border border-hairline bg-surface px-3 text-ink focus:border-ink focus:outline-none'

export default function Admin({ wards, ward }: { wards: Ward[] | null; ward: string }) {
  const [session, setSession] = useState<AdminSession | null>(adminSession.get())
  const [preview, setPreview] = useState(false)
  if (!session && !preview) return <Gate wards={wards} onLogin={(s) => { adminSession.set(s); setSession(s) }} onPreview={() => setPreview(true)} />
  return <Dashboard session={session} ward={ward} onLogout={() => { adminSession.clear(); setSession(null); setPreview(false) }} />
}

function Gate({ wards, onLogin, onPreview }: { wards: Ward[] | null; onLogin: (s: AdminSession) => void; onPreview: () => void }) {
  const [email, setEmail] = useState(''); const [password, setPassword] = useState('')
  const [login, setLogin] = useState<'idle' | 'busy' | 'pending' | 'error' | 'denied'>('idle')
  const [req, setReq] = useState({ name: '', email: '', designation: '', ward_code: 'K/W', reason: '' })
  const [reqState, setReqState] = useState<'idle' | 'busy' | 'sent' | 'pending' | 'error'>('idle')

  const doLogin = async (e: React.FormEvent) => {
    e.preventDefault(); setLogin('busy')
    try { const s = await api.login(email, password); if (s.role === 'citizen') { setLogin('denied'); return } onLogin(s) } catch (err) { setLogin(notYet(err) ? 'pending' : 'error') }
  }
  const doRequest = async (e: React.FormEvent) => {
    e.preventDefault(); setReqState('busy')
    try { await api.accessRequest(req); setReqState('sent') } catch (err) { setReqState(notYet(err) ? 'pending' : 'error') }
  }

  return (
    <div className="rise space-y-6">
      <div className="max-w-3xl space-y-2">
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Ward office</h1>
        <p className="text-muted">For ward engineers and officers: review citizen reports, move them forward, notify contractors and reply to audit flags.</p>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <form onSubmit={doLogin} className="space-y-4 rounded-[20px] border border-hairline bg-surface p-5">
          <h2 className="text-lg font-bold">Sign in</h2>
          {DEMO && <p className="rounded-[12px] border border-hairline bg-hwyellow/25 p-3 text-sm">Demo: sign in as <span className="font-semibold">officer@demo.in</span> with any password.</p>}
          <label className="block text-sm font-medium">Official email<input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className={input} /></label>
          <label className="block text-sm font-medium">Password<input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} className={input} /></label>
          <Primary type="submit" disabled={login === 'busy'} className="w-full">{login === 'busy' ? 'Signing in…' : 'Sign in'}</Primary>
          {login === 'pending' && <Pending label="Officer sign-in" />}
          {login === 'error' && <p className="text-sm">Email or password not recognised.</p>}
          {login === 'denied' && <p className="text-sm">This account is a citizen account. Request ward office access on the right.</p>}
          <button type="button" onClick={onPreview} className="w-full text-center text-sm font-semibold underline decoration-hwyellow decoration-2 underline-offset-4">Preview the dashboard without signing in</button>
        </form>
        <form onSubmit={doRequest} className="space-y-4 rounded-[20px] border border-hairline bg-surface p-5">
          <h2 className="text-lg font-bold">Request access</h2>
          {reqState === 'sent' ? <p className="rounded-[12px] border-2 border-ink bg-hwyellow/25 p-4">Request sent. An administrator will approve it, and you will get an email.</p> : <>
            <label className="block text-sm font-medium">Full name<input required value={req.name} onChange={(e) => setReq({ ...req, name: e.target.value })} className={input} /></label>
            <label className="block text-sm font-medium">Official email<input type="email" required value={req.email} onChange={(e) => setReq({ ...req, email: e.target.value })} className={input} /></label>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="block min-w-0 text-sm font-medium">Designation<input required value={req.designation} onChange={(e) => setReq({ ...req, designation: e.target.value })} placeholder="Assistant Engineer" className={input} /></label>
              <label className="block min-w-0 text-sm font-medium">Ward<select value={req.ward_code} onChange={(e) => setReq({ ...req, ward_code: e.target.value })} className={input}>
                {(wards ?? []).map((w) => <option key={w.ward_code} value={w.ward_code}>{w.ward_code} · {shortWard(w.ward_name)}</option>)}
              </select></label>
            </div>
            <label className="block text-sm font-medium">Why you need access<textarea required value={req.reason} onChange={(e) => setReq({ ...req, reason: e.target.value })} rows={2} className={`${input} py-2`} /></label>
            <button type="submit" disabled={reqState === 'busy'} className="min-h-[48px] w-full rounded-[8px] border border-ink bg-surface font-semibold hover:bg-hwyellow/20 disabled:opacity-60">{reqState === 'busy' ? 'Sending…' : 'Send request'}</button>
            {reqState === 'pending' && <Pending label="Access requests" />}
            {reqState === 'error' && <p className="text-sm">The request could not be sent. Try again.</p>}
          </>}
        </form>
      </div>
    </div>
  )
}

function Dashboard({ session, ward, onLogout }: { session: AdminSession | null; ward: string; onLogout: () => void }) {
  const [tab, setTab] = useState<'reports' | 'flags'>('reports')
  const summary = useAsync(() => api.adminSummary(ward).catch((e) => { if (notYet(e)) return null; throw e }), [ward])
  const s = summary.data
  return (
    <div className="rise space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Ward office · Ward {ward}</h1>
          <p className="text-muted">{session ? `Signed in as ${session.name ?? session.role.replace('_', ' ')}` : 'Preview mode: actions that change records need sign-in.'}</p>
        </div>
        <button onClick={onLogout} className="flex min-h-[44px] items-center gap-2 rounded-[8px] border border-hairline bg-surface px-4 text-sm font-semibold hover:border-ink"><LogOut size={16} strokeWidth={1.5} /> {session ? 'Sign out' : 'Exit preview'}</button>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {summary.loading ? [0, 1, 2, 3].map((i) => <Skel key={i} className="h-24" />) : s ? <>
          <Kpi label="New today" value={num(s.new_today)} /><Kpi label="Past SLA" value={num(s.overdue_sla)} />
          <Kpi label="Rupees held" value={inr(s.rupees_held_inr)} /><Kpi label="Flags awaiting reply" value={num(s.flags_awaiting_reply)} />
        </> : <div className="col-span-2 md:col-span-4"><Pending label="Ward office summary (new today, past SLA, rupees held)" /></div>}
      </div>

      <div role="tablist" className="grid grid-cols-2 gap-1 rounded-[12px] border border-hairline bg-surface p-[4px] sm:inline-grid">
        {(['reports', 'flags'] as const).map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)} className={`min-h-[44px] rounded-[8px] px-4 text-sm ${tab === t ? 'bg-hwyellow font-semibold' : 'font-medium text-muted'}`}>{t === 'reports' ? 'Citizen reports' : 'Flags awaiting reply'}</button>
        ))}
      </div>
      {tab === 'reports' ? <Reports ward={ward} canAct={!!session} /> : <Flags ward={ward} />}
    </div>
  )
}

function Kpi({ label, value }: { label: string; value: string }) {
  return <div className="rounded-[16px] border border-hairline bg-surface p-4"><p className="text-xs text-muted">{label}</p><p className="text-2xl font-bold">{value}</p></div>
}

function Reports({ ward, canAct }: { ward: string; canAct: boolean }) {
  const inbox = useAsync(() => api.adminReports({ ward, sort: 'oldest_open' }).catch((e) => { if (notYet(e)) return null; throw e }), [ward])
  const [id, setId] = useState('')
  const [open, setOpen] = useState<CitizenReport | null>(null)
  const [lookup, setLookup] = useState<'idle' | 'busy' | 'none'>('idle')
  const find = async (e: React.FormEvent) => {
    e.preventDefault(); if (!id.trim()) return; setLookup('busy')
    try { setOpen(await api.reportStatus(Number(id))); setLookup('idle') } catch { setLookup('none') }
  }
  return (
    <div className="space-y-4">
      <form onSubmit={find} className="flex gap-2 rounded-[16px] border border-hairline bg-surface p-3">
        <label className="relative flex-1"><span className="sr-only">Report number</span>
          <Search size={18} strokeWidth={1.5} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
          <input inputMode="numeric" value={id} onChange={(e) => setId(e.target.value.replace(/\D/g, ''))} placeholder="Open a report by number" className="min-h-[48px] w-full rounded-[8px] border border-hairline bg-concrete pl-10 pr-3 focus:border-ink focus:outline-none" />
        </label>
        <Primary type="submit" disabled={lookup === 'busy'}>Open</Primary>
      </form>
      {lookup === 'none' && <p className="text-sm">No report with that number.</p>}
      {inbox.error ? <ErrorBox error={inbox.error} onRetry={inbox.reload} /> : inbox.loading ? <div className="grid gap-3 md:grid-cols-2">{[0, 1].map((i) => <Skel key={i} className="h-32" />)}</div>
        : inbox.data === null ? <Pending label={`Report inbox for ward ${ward} (oldest open first, with filters)`} />
        : inbox.data.length === 0 ? <p className="text-sm text-muted">No open reports in this ward.</p>
        : <div className="grid gap-3 md:grid-cols-2">{inbox.data.map((r) => (
          <button key={r.id} onClick={() => setOpen(r)} className="space-y-2 rounded-[16px] border border-hairline bg-surface p-4 text-left hover:border-ink">
            <div className="flex items-start justify-between gap-3"><p className="font-bold">Report {r.id}</p><span className="shrink-0 rounded-[8px] bg-hwyellow px-2 py-1 text-xs font-semibold">{statusLabel(r.status)}</span></div>
            <p className="text-sm">{(r.text ?? '').split('\n')[0]}</p>
            <p className="flex flex-wrap items-center gap-2 text-xs text-muted">{r.road_id && <Id>{r.road_id}</Id>}<span>{date(r.created_at)}</span></p>
          </button>))}</div>}
      {open && <ReportPanel report={open} canAct={canAct} onClose={() => setOpen(null)} onChanged={setOpen} />}
    </div>
  )
}

function ReportPanel({ report, canAct, onClose, onChanged }: { report: CitizenReport; canAct: boolean; onClose: () => void; onChanged: (r: CitizenReport) => void }) {
  const [note, setNote] = useState('')
  const [state, setState] = useState<'idle' | 'busy' | 'pending' | 'error' | 'done'>('idle')
  const act = async (status: string) => {
    setState('busy')
    try { onChanged(await api.adminUpdate(report.id, { status, note: note.trim() || undefined, rejection_reason: status === 'rejected' ? note.trim() || undefined : undefined })); setNote(''); setState('done') }
    catch (e) { setState(notYet(e) ? 'pending' : 'error') }
  }
  const notify = async () => {
    setState('busy')
    try { await api.notifyContractor(report.id, 'email'); onChanged(await api.reportStatus(report.id)); setState('done') } catch (e) { setState(notYet(e) ? 'pending' : 'error') }
  }
  const next = NEXT[report.status] ?? []
  return (
    <Modal title={`Report ${report.id} · ${statusLabel(report.status)}`} onClose={onClose}>
      <div className="space-y-5">
        <div className="space-y-1 rounded-[12px] border border-hairline bg-concrete p-4 text-sm">
          {(report.text ?? '').split('\n').filter(Boolean).map((l) => <p key={l}>{l}</p>)}
          <p className="flex flex-wrap items-center gap-2 text-muted">{report.road_id && <Id>{report.road_id}</Id>}{report.flag_id && <Id>{report.flag_id}</Id>}<span>{date(report.created_at)}</span></p>
        </div>
        <Tracker report={report} />
        <div className="space-y-3 rounded-[12px] border border-hairline p-4">
          <p className="font-semibold">Move this report forward</p>
          {!canAct && <p className="text-sm text-muted">Sign in to change the status. In preview, actions are disabled.</p>}
          <label className="block text-sm font-medium">Note for the citizen (shown on their tracker)<textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} maxLength={500} className={`${input} py-2`} /></label>
          <div className="grid gap-2 sm:grid-cols-2">
            {next.map((st) => (
              <button key={st} onClick={() => act(st)} disabled={!canAct || state === 'busy'} className={`min-h-[48px] rounded-[8px] px-3 text-sm font-semibold disabled:opacity-50 ${st === 'rejected' ? 'border border-ink bg-surface' : 'bg-hwyellow hover:bg-hwyellow-strong'}`}>
                {st === 'rejected' ? 'Close with reason' : `Mark: ${statusLabel(st)}`}
              </button>
            ))}
            <button onClick={notify} disabled={!canAct || state === 'busy'} className="min-h-[48px] rounded-[8px] border border-ink bg-surface px-3 text-sm font-semibold disabled:opacity-50">Notify contractor</button>
          </div>
          {next.length === 0 && <p className="text-sm text-muted">This report is closed.</p>}
          {state === 'pending' && <Pending label="Changing report status" />}
          {state === 'error' && <p className="text-sm">That change was not allowed or did not save.</p>}
          {state === 'done' && <p className="text-sm">Saved. The citizen sees this on their tracker.</p>}
        </div>
      </div>
    </Modal>
  )
}

/** Live now: flagged bills in this ward with no reply yet, from the public flagged queue. */
function Flags({ ward }: { ward: string }) {
  const q = useAsync(() => api.queue(ward, 30), [ward])
  const [open, setOpen] = useState<QueueItem | null>(null)
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />
  if (q.loading || !q.data) return <div className="grid gap-3 md:grid-cols-2">{[0, 1].map((i) => <Skel key={i} className="h-32" />)}</div>
  const waiting = q.data.filter((f) => f.replies_count === 0)
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted">{num(waiting.length)} of {num(q.data.length)} top flagged bills in ward {ward} have no reply yet.</p>
      <div className="grid gap-3 md:grid-cols-2">
        {waiting.map((f) => (
          <article key={f.work_order_id} className="space-y-2 rounded-[16px] border border-hairline bg-surface p-4">
            <div className="flex items-start justify-between gap-3"><h3 className="font-bold">{f.road_name}</h3><p className="shrink-0 text-lg font-bold">{inr(f.rupees_at_stake)}</p></div>
            <p className="text-sm">{f.detectors.map((d) => DETECTOR[d] ?? d).join(', ')}</p>
            <p className="flex flex-wrap items-center gap-2 text-xs text-muted"><Id>{f.work_order_id}</Id><span>{cleanName(f.contractor_name)}</span></p>
            <button onClick={() => setOpen(f)} className="min-h-[44px] w-full rounded-[8px] border border-ink bg-surface text-sm font-semibold hover:bg-hwyellow/20">Reply on the record</button>
          </article>
        ))}
      </div>
      {open && <ReplyModal item={open} onClose={() => setOpen(null)} onDone={() => { setOpen(null); q.reload() }} />}
    </div>
  )
}

function ReplyModal({ item, onClose, onDone }: { item: QueueItem; onClose: () => void; onDone: () => void }) {
  const [body, setBody] = useState(''); const [state, setState] = useState<'idle' | 'busy' | 'error'>('idle')
  const send = async () => {
    setState('busy')
    try { await api.reply(item.flag_ids[0], { author_role: 'ward_engineer', body: body.trim() }); onDone() } catch { setState('error') }
  }
  return (
    <Modal title={`Reply: ${item.road_name}`} onClose={onClose} footer={<Primary onClick={send} disabled={!body.trim() || state === 'busy'} className="w-full">{state === 'busy' ? 'Saving…' : 'Save reply'}</Primary>}>
      <div className="space-y-3">
        <p className="text-sm text-muted">Flag <Id>{item.flag_ids[0]}</Id> on <Id>{item.work_order_id}</Id>. Replies are public and attached to the flag.</p>
        <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={4} maxLength={4000} placeholder="For example: utility trench permit MGL/2025/118 reopened this stretch." className={`${input} py-2`} />
        {state === 'error' && <p className="text-sm">The reply could not be saved.</p>}
      </div>
    </Modal>
  )
}
