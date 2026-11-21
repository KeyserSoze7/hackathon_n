import { useState } from 'react'
import { Check, RotateCw } from 'lucide-react'
import { api, myReports, notYet, session } from '../data/api'
import { useAsync } from '../lib/useAsync'
import { date, inr, num } from '../lib/format'
import type { CitizenReport, Me as MeT } from '../data/types'
import { ErrorBox, Id, Modal, Pending, Primary, Skel } from '../components/ui'
import Tracker, { statusLabel } from '../components/Tracker'

const OPEN = (s: string) => s !== 'resolved' && s !== 'rejected'
const firstLine = (t: string | null) => (t ?? '').split('\n')[0].replace(/^Issue: /, '')

/** Citizen profile without login: reports sent from this device, their status, and what they contributed. */
export default function Me({ onFind, onOpenRoad }: { onFind: () => void; onOpenRoad: (id: string) => void }) {
  // Server profile when it exists (GET /api/me); otherwise build it from this device's report ids.
  const me = useAsync<MeT | null>(() => api.me().catch((e) => { if (notYet(e)) return null; throw e }), [])
  const reports = useAsync(() => Promise.all(myReports.ids().map((id) => api.reportStatus(id).catch(() => null))).then((r) => r.filter((x): x is CitizenReport => !!x).sort((a, b) => b.id - a.id)), [])
  const [open, setOpen] = useState<CitizenReport | null>(null)

  if (reports.error) return <ErrorBox error={reports.error} onRetry={reports.reload} />
  const list = reports.data ?? []
  const s = me.data?.stats
  const roads = new Set(list.map((r) => r.road_id).filter(Boolean)).size
  const matched = list.filter((r) => r.flag_id).length

  return (
    <div className="rise space-y-6">
      <div className="max-w-3xl space-y-2">
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">My reports</h1>
        <p className="text-muted">Reports sent from this device, where each one is now, and what they led to. No login needed.</p>
      </div>

      <Account onChange={() => { me.reload(); reports.reload() }} />

      {reports.loading ? <div className="grid grid-cols-2 gap-3 md:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skel key={i} className="h-24" />)}</div> : (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Reports sent" value={num(s?.reports ?? list.length)} />
          <Stat label="Roads covered" value={num(s?.roads ?? roads)} />
          <Stat label="Still open" value={num(s?.open ?? list.filter((r) => OPEN(r.status)).length)} />
          <Stat label="Matched to a flagged bill" value={num(matched)} />
          <div className="col-span-2 rounded-[16px] border-2 border-ink bg-surface p-4 md:col-span-4">
            <p className="text-xs text-muted">Rupees on flagged bills your reports are linked to</p>
            {s ? <p className="text-3xl font-bold">{inr(s.rupees_flagged_inr)} <span className="text-base font-normal text-muted">· {inr(s.rupees_held_inr)} held</span></p> : <Pending className="mt-2" label="Your contribution in rupees" />}
          </div>
        </div>
      )}

      {!reports.loading && list.length === 0 ? (
        <div className="space-y-4 rounded-[20px] border border-hairline bg-surface p-6 text-center">
          <p className="font-semibold">No reports from this device yet.</p>
          <p className="text-sm text-muted">Find a road, then use “Report a problem on this road”.</p>
          <Primary onClick={onFind} className="mx-auto">Find a road</Primary>
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {list.map((r) => (
            <button key={r.id} onClick={() => setOpen(r)} className="space-y-2 rounded-[16px] border border-hairline bg-surface p-4 text-left hover:border-ink">
              <div className="flex items-start justify-between gap-3">
                <p className="font-bold">Report {r.id}: {firstLine(r.text) || r.kind.replace(/_/g, ' ')}</p>
                <span className={`shrink-0 rounded-[8px] px-2 py-1 text-xs font-semibold ${OPEN(r.status) ? 'bg-hwyellow' : 'bg-concrete'}`}>{statusLabel(r.status)}</span>
              </div>
              <p className="flex flex-wrap items-center gap-2 text-sm text-muted">{r.road_id && <Id>{r.road_id}</Id>}<span>Sent {date(r.created_at)}</span></p>
              {r.flag_id && <p className="text-sm">Linked to flagged bill <Id>{r.flag_id.split(':').pop() ?? r.flag_id}</Id></p>}
            </button>
          ))}
        </div>
      )}

      <p className="text-center text-sm text-muted">Ward engineer or officer? <a href="#admin" className="font-semibold text-ink underline decoration-hwyellow decoration-2 underline-offset-4">Open the ward office</a></p>

      {open && <ReportDetail report={open} onClose={() => setOpen(null)} onOpenRoad={onOpenRoad} onChanged={(r) => { setOpen(r); reports.reload() }} />}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return <div className="rounded-[16px] border border-hairline bg-surface p-4"><p className="text-xs text-muted">{label}</p><p className="text-2xl font-bold">{value}</p></div>
}

function ReportDetail({ report, onClose, onOpenRoad, onChanged }: { report: CitizenReport; onClose: () => void; onOpenRoad: (id: string) => void; onChanged: (r: CitizenReport) => void }) {
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<'pending' | 'error' | null>(null)
  const refresh = async () => { setBusy(true); try { onChanged(await api.reportStatus(report.id)) } catch { /* keep */ } setBusy(false) }
  const confirm = async (fixed: boolean) => {
    setBusy(true); setMsg(null)
    try { onChanged(await api.confirm(report.id, fixed)) } catch (e) { setMsg(notYet(e) ? 'pending' : 'error') }
    setBusy(false)
  }
  return (
    <Modal title={`Report ${report.id}`} onClose={onClose} footer={
      <div className="flex gap-2">
        {report.road_id && <button onClick={() => { onClose(); onOpenRoad(report.road_id!) }} className="min-h-[48px] flex-1 rounded-[8px] border border-hairline bg-surface px-4 text-sm font-semibold hover:border-ink">Road receipt</button>}
        <Primary onClick={onClose} className="flex-1">Done</Primary>
      </div>
    }>
      <div className="space-y-5">
        <div className="space-y-1 rounded-[12px] border border-hairline bg-concrete p-4 text-sm">
          {(report.text ?? '').split('\n').filter(Boolean).map((l) => <p key={l}>{l}</p>)}
          <p className="text-muted">Sent {date(report.created_at)} · {report.kind.replace(/_/g, ' ')}</p>
        </div>
        <div className="flex items-center justify-between gap-3">
          <h3 className="font-bold">Where it is now</h3>
          <button onClick={refresh} disabled={busy} className="flex min-h-[40px] items-center gap-2 rounded-[8px] border border-hairline bg-surface px-3 text-sm font-semibold hover:border-ink disabled:opacity-60"><RotateCw size={14} strokeWidth={1.5} /> Refresh</button>
        </div>
        <Tracker report={report} />
        <div className="space-y-2 rounded-[12px] border border-hairline p-4">
          <p className="font-semibold">Has it been fixed?</p>
          <div className="grid grid-cols-2 gap-2">
            <button onClick={() => confirm(true)} disabled={busy} className="flex min-h-[48px] items-center justify-center gap-2 rounded-[8px] border border-ink bg-surface font-semibold hover:bg-hwyellow/20 disabled:opacity-60"><Check size={16} strokeWidth={1.5} /> Yes, fixed</button>
            <button onClick={() => confirm(false)} disabled={busy} className="min-h-[48px] rounded-[8px] border border-ink bg-surface font-semibold hover:bg-hwyellow/20 disabled:opacity-60">Still broken</button>
          </div>
          {msg === 'pending' && <Pending label="Confirming a fix" />}
          {msg === 'error' && <p className="text-sm">That did not go through. Try again.</p>}
        </div>
      </div>
    </Modal>
  )
}

/** Email and password account. Signing in ties reports to the person, not just this device. */
function Account({ onChange }: { onChange: () => void }) {
  const [user, setUser] = useState(session.get())
  const [mode, setMode] = useState<'login' | 'signup'>('login')
  const [f, setF] = useState({ name: '', email: '', password: '' })
  const [state, setState] = useState<'idle' | 'busy' | 'pending' | 'error'>('idle')
  const field = 'mt-1.5 min-h-[48px] w-full rounded-[8px] border border-hairline bg-surface px-3 focus:border-ink focus:outline-none'
  if (user) return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-[16px] border border-hairline bg-surface p-4">
      <p className="text-sm">Signed in as <span className="font-semibold">{user.name ?? user.email}</span>{user.role !== 'citizen' ? ` · ${user.role.replace('_', ' ')}` : ''}</p>
      <button onClick={() => { session.clear(); setUser(null); onChange() }} className="min-h-[44px] rounded-[8px] border border-hairline px-4 text-sm font-semibold hover:border-ink">Sign out</button>
    </div>
  )
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setState('busy')
    try {
      const s = mode === 'login' ? await api.login(f.email, f.password) : await api.signup(f.name, f.email, f.password)
      session.set(s); setUser(s); setState('idle'); onChange()
    } catch (err) { setState(notYet(err) ? 'pending' : 'error') }
  }
  return (
    <form onSubmit={submit} className="space-y-3 rounded-[16px] border border-hairline bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-semibold">{mode === 'login' ? 'Sign in to keep your reports on any device' : 'Create your account'}</p>
        <button type="button" onClick={() => setMode(mode === 'login' ? 'signup' : 'login')} className="text-sm font-semibold underline decoration-hwyellow decoration-2 underline-offset-4">{mode === 'login' ? 'Create account' : 'I have an account'}</button>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        {mode === 'signup' && <label className="block min-w-0 text-sm font-medium">Name<input required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} className={field} /></label>}
        <label className="block min-w-0 text-sm font-medium">Email<input type="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} className={field} /></label>
        <label className="block min-w-0 text-sm font-medium">Password<input type="password" required minLength={6} value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} className={field} /></label>
      </div>
      <Primary type="submit" disabled={state === 'busy'} className="w-full sm:w-auto">{state === 'busy' ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}</Primary>
      {state === 'pending' && <Pending label="Email and password sign-in" />}
      {state === 'error' && <p className="text-sm">Email or password not recognised.</p>}
      <p className="text-xs text-muted">No account needed to report. Reports sent from this device always appear here.</p>
    </form>
  )
}
