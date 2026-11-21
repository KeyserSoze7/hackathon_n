// Demo mode (VITE_DEMO=1): the app runs with no backend. Reads are served from saved snapshots of the real API
// (frontend/public/demo/, written by scripts/capture_demo.py). Anything a visitor sends (reports, replies, sign-in,
// ward-office actions) is kept in their own browser only. Same screens, same code paths as the live site.
import type { CitizenReport, QueueItem, RoadDetail, Reply, AdminSession, AdminSummary } from './types'

export const DEMO = (import.meta.env.VITE_DEMO as string | undefined) === '1'

export class DemoMiss extends Error {
  constructor(public status = 404) { super('not in demo data') }
}

const BASE = `${import.meta.env.BASE_URL}demo/`
type Manifest = { files: Record<string, string>; samples: { queries: string[]; lookups: string[] } }
let manifest: Promise<Manifest> | null = null
const cache = new Map<string, Promise<unknown>>()

const loadManifest = () => (manifest ??= fetch(BASE + 'manifest.json').then((r) => { if (!r.ok) throw new DemoMiss(500); return r.json() }))
async function load<T>(key: string): Promise<T> {
  const m = await loadManifest()
  const file = m.files[key]
  if (!file) throw new DemoMiss()
  if (!cache.has(file)) cache.set(file, fetch(BASE + file).then((r) => { if (!r.ok) throw new DemoMiss(); return r.json() }))
  return (await cache.get(file)) as T
}
export const demoSamples = async () => (await loadManifest()).samples

// ---- the visitor's own data (reports, replies) ----
const KEY = 'marg-demo-store'
interface Store { next: number; reports: Record<string, DemoReport>; replies: Record<string, Reply[]> }
type DemoReport = CitizenReport & { events: NonNullable<CitizenReport['events']> }
const readStore = (): Store => { try { return JSON.parse(localStorage.getItem(KEY) ?? '') as Store } catch { return { next: 9001, reports: {}, replies: {} } } }
const writeStore = (s: Store) => localStorage.setItem(KEY, JSON.stringify(s))
export const demoReportIds = () => Object.keys(readStore().reports).map(Number)

const LABEL: Record<string, string> = {
  reported: 'Reported', matched_to_contract: 'Matched to contract', under_review: 'Under review', payment_held: 'Payment held (warranty)',
  contractor_notified: 'Contractor notified', repair_scheduled: 'Repair scheduled', resolved: 'Marked fixed', rejected: 'Closed',
}
const STEPS = ['reported', 'matched_to_contract', 'payment_held', 'contractor_notified']
const now = () => new Date().toISOString()
function withTracker(r: DemoReport): DemoReport {
  const seen = new Set(r.events.map((e) => e.status))
  const nextIdx = STEPS.findIndex((s) => !seen.has(s))
  r.tracker = STEPS.map((step, i) => ({ step, label: LABEL[step], done: seen.has(step), status: seen.has(step) ? 'done' : i === nextIdx ? 'current' : 'pending', at: r.events.find((e) => e.status === step)?.at ?? null }))
  return r
}
function addEvent(r: DemoReport, status: string, by_role: string, note?: string) {
  r.events.push({ status, at: now(), by_role, note }); r.status = status; r.status_updated_at = now(); return withTracker(r)
}

async function createReport(body: Record<string, unknown>): Promise<DemoReport> {
  const road = body.road_id ? await load<RoadDetail>(`road:${body.road_id}`).catch(() => null) : null
  const flag = road?.flags.find((f) => f.detector === 'DLP_PAID_TWICE') ?? null
  const under = !!(road?.under_dlp && flag)
  const s = readStore(); const id = s.next++
  const wo = flag ? road!.work_orders.find((w) => w.work_order_id === flag.work_order_id) : null
  const r: DemoReport = {
    id, kind: String(body.kind), input_mode: String(body.input_mode ?? 'text'), text: (body.text as string) ?? null, language: (body.language as string) ?? 'en',
    photo_url: null, matched_locality: (body.matched_locality as string) ?? null, road_id: (body.road_id as string) ?? null, work_order_id: null,
    flag_id: under ? flag!.flag_id : null, status: 'reported', status_updated_at: now(), created_at: now(), tracker: [], events: [],
    road: road ? { road_id: road.road_id, road_name: road.road_name, ward_code: road.ward_code, under_dlp: road.under_dlp } : null,
    responsible: road ? { party: under ? 'contractor_under_dlp' : 'bmc_ward', name: under && wo ? wo.contractor_name : `${road.ward_code} Ward Office`, ward_office: `${road.ward_code} Ward Office (synthetic)`,
      basis: under ? "This road is under the original contractor's Defect Liability Period, so surface defects are the contractor's to fix at no cost to BMC." : 'This road is out of warranty, so repairs are the ward office’s.' } : null,
  }
  addEvent(r, 'reported', 'citizen'); addEvent(r, 'matched_to_contract', 'system')
  if (under) addEvent(r, 'payment_held', 'system', 'Payment on the matched bill is held while the contractor is asked to fix it under warranty.')
  s.reports[id] = r; writeStore(s); return r
}

const norm = (t: string) => t.toLowerCase().replace(/[^\p{L}\p{N} ]/gu, ' ').replace(/\s+/g, ' ').trim()

/** Find a saved answer whose road or place appears in the visitor's text. */
function pick<T extends { matched_text?: string; matched_locality?: string | null; road?: { road_name?: string } }>(items: { q: string; result: T }[], text: string) {
  const t = ` ${norm(text)} `
  let best: { result: T; score: number } | null = null
  for (const { q, result } of items) {
    const names = [result.matched_text, result.matched_locality, result.road?.road_name, q].filter((x): x is string => !!x).map(norm)
    for (const n of names) if (n.length > 3 && t.includes(` ${n} `) && (!best || n.length > best.score)) best = { result, score: n.length }
  }
  return best?.result ?? null
}

// ---- reads ----
export async function demoGet(path: string): Promise<unknown> {
  const u = new URL(path, 'http://demo'); const p = u.pathname; const sp = u.searchParams
  const seg = p.split('/').map(decodeURIComponent)

  if (p === '/api/flagged-queue') {
    const ward = sp.get('ward'); const list = await load<QueueItem[]>(`queue:${ward ?? 'ALL'}`)
    const replies = readStore().replies
    return list.slice(0, Number(sp.get('limit') ?? 5)).map((q) => ({ ...q, replies_count: q.replies_count + (replies[q.flag_ids[0]]?.length ?? 0) }))
  }
  if (p === '/api/roads') {
    const all = await load<Record<string, unknown>[]>('roadlist'); const q = norm(sp.get('q') ?? ''); const ward = sp.get('ward')
    const hit = all.filter((r) => (!ward || r.ward_code === ward) && (!q || norm(`${r.road_name} ${r.road_id} ${r.ward_code}`).includes(q)))
    const off = Number(sp.get('offset') ?? 0)
    return hit.slice(off, off + Number(sp.get('limit') ?? 20))
  }
  if (seg[2] === 'roads' && seg.length === 4) {
    const road = await load<RoadDetail>(`road:${seg[3]}`); const rep = readStore().replies
    return { ...road, flags: road.flags.map((f) => ({ ...f, replies: [...f.replies, ...(rep[f.flag_id] ?? [])] })) }
  }
  if (seg[2] === 'roads' && seg[4] === 'timeline') return load(`timeline:${seg[3]}`)
  if (p === '/api/lookup') {
    const hit = pick(await load<{ q: string; result: Record<string, never> & { matched_text?: string; matched_locality?: string | null; road?: { road_name?: string } } }[]>('lookups'), sp.get('q') ?? '')
    if (!hit) throw new DemoMiss(); return hit
  }
  if (p === '/api/livability') return load(`livability:${sp.get('locality')}`)
  if (seg[2] === 'v3' && seg[3] === 'next-rupee') return load(`next:${seg[4]}`)
  if (seg[2] === 'wards' && seg[4] === 'money-trail') return load(`trail:${seg[3]}`)
  if (seg[2] === 'citizen-reports') {
    const r = readStore().reports[seg[3]]; if (!r) throw new DemoMiss(); return r
  }
  if (p === '/api/admin/reports') {
    const ward = sp.get('ward'); return Object.values(readStore().reports).filter((r) => !ward || r.road?.ward_code === ward).sort((a, b) => b.id - a.id)
  }
  if (p === '/api/admin/summary') return adminSummary(sp.get('ward'))
  if (p === '/api/me') throw new DemoMiss()
  return load(p)
}

async function adminSummary(ward: string | null): Promise<AdminSummary> {
  const reps = Object.values(readStore().reports).filter((r) => !ward || r.road?.ward_code === ward)
  const by: Record<string, number> = {}; reps.forEach((r) => { by[r.status] = (by[r.status] ?? 0) + 1 })
  const queue = await load<QueueItem[]>(`queue:${ward ?? 'ALL'}`).catch(() => [])
  const replies = readStore().replies
  const held = (await Promise.all(reps.filter((r) => r.status === 'payment_held' && r.flag_id).map(async (r) => {
    const road = await load<RoadDetail>(`road:${r.road_id}`).catch(() => null); return road?.flags.find((f) => f.flag_id === r.flag_id)?.rupees_at_stake ?? 0
  }))).reduce((a, b) => a + b, 0)
  return { reports_by_status: by, new_today: reps.length, overdue_sla: 0, median_hours_to_resolve: null, rupees_held_inr: held, flags_awaiting_reply: queue.filter((q) => q.replies_count + (replies[q.flag_ids[0]]?.length ?? 0) === 0).length }
}

// ---- writes ----
export async function demoSend(method: 'POST' | 'PATCH', path: string, body: Record<string, unknown>): Promise<unknown> {
  const seg = path.split('/').map(decodeURIComponent)
  if (path === '/api/v3/allocate') {
    const grid = await load<{ budget: number; resp: Record<string, unknown> }[]>(`alloc:${body.ward_code}`)
    const ok = grid.filter((g) => g.budget <= Number(body.budget_inr))
    return (ok.length ? ok[ok.length - 1] : grid[0]).resp
  }
  if (path === '/api/citizen-query') {
    const hit = pick(await load<{ q: string; result: Record<string, never> & { matched_text?: string; matched_locality?: string | null; road?: { road_name?: string } } }[]>('queries'), String(body.text ?? ''))
    if (!hit) throw new DemoMiss(); return hit
  }
  if (path === '/api/draft-notice') {
    const n = await load<Record<string, Record<string, unknown>>>('notices'); const r = n[String(body.road_id)]?.[String(body.language)]
    if (!r) throw new DemoMiss(); return r
  }
  if (path === '/api/auth/login' || path === '/api/auth/signup') {
    const email = String(body.email ?? ''); const staff = /officer|admin/i.test(email)
    const s: AdminSession = { token: `demo-${staff ? 'officer' : 'citizen'}`, role: staff ? 'ward_officer' : 'citizen', name: String(body.name ?? email.split('@')[0]), email, ward_codes: [] }
    return s
  }
  if (path === '/api/admin/access-requests') return { request_id: 1, status: 'pending' }
  if (path === '/api/citizen-reports') return createReport(body)
  if (seg[2] === 'citizen-reports' && seg[4] === 'confirm') {
    const s = readStore(); const r = s.reports[seg[3]]; if (!r) throw new DemoMiss()
    addEvent(r, body.fixed ? 'resolved' : 'under_review', 'citizen', body.fixed ? 'Citizen confirmed the repair is holding.' : 'Citizen says it is still broken; reopened for review.'); writeStore(s); return r
  }
  if (seg[2] === 'flags' && seg[4] === 'replies') {
    const s = readStore(); const list = (s.replies[seg[3]] ??= [])
    list.push({ author_role: String(body.author_role), author_name: (body.author_name as string) ?? null, body: String(body.body), created_at: now() }); writeStore(s); return list[list.length - 1]
  }
  if (seg[2] === 'admin' && seg[3] === 'reports') {
    const s = readStore(); const r = s.reports[seg[4]]; if (!r) throw new DemoMiss()
    if (seg[5] === 'notify-contractor') addEvent(r, 'contractor_notified', 'ward_officer', `Contractor notified by ${body.channel}.`)
    else addEvent(r, String(body.status), 'ward_officer', (body.note as string) || (body.rejection_reason as string) || undefined)
    writeStore(s); return r
  }
  throw new DemoMiss(method === 'POST' ? 404 : 405)
}
