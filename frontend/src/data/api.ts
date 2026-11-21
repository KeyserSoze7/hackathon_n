// Live backend client. No sample fallbacks: anything the API does not serve yet is shown as "Data coming in".
import type {
  City, Ward, QueueItem, CitizenReport, RoadDetail, TimelineEvent, Lookup, Contractor, AllocWard, NextItem, Allocation, CitizenReportReq,
  Me, AdminSession, AdminSummary, AccessRequestReq, CitizenQueryRes, Notice, MoneyTrail,
  Locality, Livability, RoadListItem,
} from './types'

export const API_BASE: string = (import.meta.env.VITE_API_BASE as string | undefined) ?? 'http://10.10.38.50:8000'

export class ApiError extends Error {
  constructor(public status: number, public path: string) { super(`${status} ${path}`) }
}
/** True when the backend has not shipped this endpoint yet: show "Data coming in", not an error. */
export const notYet = (e: unknown) => e instanceof ApiError && (e.status === 404 || e.status === 405 || e.status === 501)

// Identity: one email/password account for citizens and officers (POST /api/auth/login). The role decides ward-office access.
// Without an account, reports are still tied to this device (myReports below).
const SESSION_KEY = 'marg-session'
export const adminSession = {
  get: (): AdminSession | null => { try { return JSON.parse(localStorage.getItem(SESSION_KEY) ?? 'null') } catch { return null } },
  set: (s: AdminSession) => localStorage.setItem(SESSION_KEY, JSON.stringify(s)),
  clear: () => localStorage.removeItem(SESSION_KEY),
}
export const session = adminSession
export const citizenToken = () => adminSession.get()?.token ?? null
const auth = (who: 'citizen' | 'admin' | 'none'): Record<string, string> => {
  const t = who === 'citizen' ? citizenToken() : who === 'admin' ? adminSession.get()?.token : null
  return t ? { Authorization: `Bearer ${t}` } : {}
}

/** Reports sent from this device. Interim "My reports" until GET /api/me/reports exists. */
const MY_KEY = 'marg-my-reports'
export const myReports = {
  ids: (): number[] => { try { return JSON.parse(localStorage.getItem(MY_KEY) ?? '[]') } catch { return [] } },
  add: (id: number) => { const s = new Set(myReports.ids()); s.add(id); localStorage.setItem(MY_KEY, JSON.stringify([...s])) },
}

async function get<T>(path: string, who: 'citizen' | 'admin' | 'none' = 'none'): Promise<T> {
  const r = await fetch(API_BASE + path, { headers: auth(who) })
  if (!r.ok) throw new ApiError(r.status, path)
  return r.json()
}
async function send<T>(method: 'POST' | 'PATCH', path: string, body: unknown, who: 'citizen' | 'admin' | 'none' = 'none'): Promise<T> {
  const r = await fetch(API_BASE + path, { method, headers: { 'content-type': 'application/json', ...auth(who) }, body: JSON.stringify(body) })
  if (!r.ok) throw new ApiError(r.status, path)
  return r.json()
}
/** The backend returns two report shapes (POST: id, road_id; GET: report_id, road{}); normalise to one. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const normReport = (r: any): CitizenReport => ({
  ...r,
  id: r.id ?? r.report_id,
  road_id: r.road_id ?? r.road?.road_id ?? null,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  tracker: (r.tracker ?? []).map((t: any) => ({ ...t, done: t.done ?? t.status === 'done' })),
})
const post = <T,>(path: string, body: unknown, who: 'citizen' | 'admin' | 'none' = 'none') => send<T>('POST', path, body, who)
const q = encodeURIComponent

export const api = {
  city: () => get<City>('/api/city'),
  wards: () => get<Ward[]>('/api/wards'),
  queue: (ward?: string, limit = 5) => get<QueueItem[]>(`/api/flagged-queue?limit=${limit}${ward ? `&ward=${q(ward)}` : ''}`),
  road: (id: string) => get<RoadDetail>(`/api/roads/${q(id)}`),
  timeline: (id: string) => get<TimelineEvent[]>(`/api/roads/${q(id)}/timeline`),
  lookup: (text: string) => get<Lookup>(`/api/lookup?q=${q(text)}`),
  localities: () => get<Locality[]>('/api/localities'),
  roads: (opts: { q?: string; ward?: string; limit?: number; offset?: number }) =>
    get<RoadListItem[]>(`/api/roads?limit=${opts.limit ?? 20}&offset=${opts.offset ?? 0}${opts.q ? `&q=${q(opts.q)}` : ''}${opts.ward ? `&ward=${q(opts.ward)}` : ''}`),
  livability: (locality: string) => get<Livability>(`/api/livability?locality=${q(locality)}`),
  contractors: () => get<Contractor[]>('/api/v3/contractors'),
  allocWards: () => get<AllocWard[]>('/api/v3/wards'),
  nextRupee: (ward: string) => get<NextItem[]>(`/api/v3/next-rupee/${q(ward)}`),
  allocate: (ward_code: string, budget_inr: number) => post<Allocation>('/api/v3/allocate', { ward_code, budget_inr }),
  reply: (flagId: string, body: { author_role: 'ward_engineer' | 'contractor' | 'other'; author_name?: string; body: string }) =>
    post<unknown>(`/api/flags/${q(flagId)}/replies`, body, 'admin'),

  // Citizen
  report: (body: CitizenReportReq) => post<unknown>('/api/citizen-reports', body, 'citizen').then(normReport),
  reportStatus: (id: number) => get<unknown>(`/api/citizen-reports/${id}`, 'citizen').then(normReport),
  me: () => get<Me>('/api/me', 'citizen'),
  confirm: (id: number, fixed: boolean, note?: string) => post<unknown>(`/api/citizen-reports/${id}/confirm`, { fixed, note }, 'citizen').then(normReport),

  // Ward office (admin)
  login: (email: string, password: string) => post<AdminSession>('/api/auth/login', { email, password }),
  signup: (name: string, email: string, password: string) => post<AdminSession>('/api/auth/signup', { name, email, password }),
  adminLogin: (email: string, password: string) => post<AdminSession>('/api/auth/login', { email, password }),
  moneyTrail: (ward: string) => get<MoneyTrail>(`/api/wards/${q(ward)}/money-trail`),
  citizenQuery: (text: string, language: 'en' | 'hi' | 'mr' = 'en') => post<CitizenQueryRes>('/api/citizen-query', { text, language, mode: 'street_check' }),
  draftNotice: (road_id: string, language: 'en' | 'hi' | 'mr', doc_type: 'defect_notice' | 'rti' = 'defect_notice') => post<Notice>('/api/draft-notice', { road_id, language, doc_type }),
  accessRequest: (body: AccessRequestReq) => post<{ request_id: number; status: string }>('/api/admin/access-requests', body),
  adminSummary: (ward?: string) => get<AdminSummary>(`/api/admin/summary${ward ? `?ward=${q(ward)}` : ''}`, 'admin'),
  adminReports: (params: Record<string, string>) => get<unknown[]>(`/api/admin/reports?${new URLSearchParams(params)}`, 'admin').then((l) => l.map(normReport)),
  adminUpdate: (id: number, body: { status: string; note?: string; rejection_reason?: string }) => send<unknown>('PATCH', `/api/admin/reports/${id}`, body, 'admin').then(normReport),
  notifyContractor: (id: number, channel: 'email' | 'sms' | 'letter') => post<unknown>(`/api/admin/reports/${id}/notify-contractor`, { channel }, 'admin'),
}
