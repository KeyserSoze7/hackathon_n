// Live backend client. No sample fallbacks: anything the API does not serve yet is shown as "Data coming in".
import type {
  City, Ward, QueueItem, RoadDetail, TimelineEvent, Lookup, Contractor, AllocWard, NextItem, Allocation, CitizenReportReq,
} from './types'

export const API_BASE: string = (import.meta.env.VITE_API_BASE as string | undefined) ?? 'http://10.10.38.50:8000'

export class ApiError extends Error {
  constructor(public status: number, public path: string) { super(`${status} ${path}`) }
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(API_BASE + path)
  if (!r.ok) throw new ApiError(r.status, path)
  return r.json()
}
async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(API_BASE + path, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })
  if (!r.ok) throw new ApiError(r.status, path)
  return r.json()
}
const q = encodeURIComponent

export const api = {
  city: () => get<City>('/api/city'),
  wards: () => get<Ward[]>('/api/wards'),
  queue: (ward?: string, limit = 5) => get<QueueItem[]>(`/api/flagged-queue?limit=${limit}${ward ? `&ward=${q(ward)}` : ''}`),
  road: (id: string) => get<RoadDetail>(`/api/roads/${q(id)}`),
  timeline: (id: string) => get<TimelineEvent[]>(`/api/roads/${q(id)}/timeline`),
  lookup: (text: string) => get<Lookup>(`/api/lookup?q=${q(text)}`),
  contractors: () => get<Contractor[]>('/api/v3/contractors'),
  allocWards: () => get<AllocWard[]>('/api/v3/wards'),
  nextRupee: (ward: string) => get<NextItem[]>(`/api/v3/next-rupee/${q(ward)}`),
  allocate: (ward_code: string, budget_inr: number) => post<Allocation>('/api/v3/allocate', { ward_code, budget_inr }),
  reply: (flagId: string, body: { author_role: 'ward_engineer' | 'contractor' | 'other'; author_name?: string; body: string }) =>
    post<unknown>(`/api/flags/${q(flagId)}/replies`, body),
  report: (body: CitizenReportReq) => post<Record<string, unknown>>('/api/citizen-reports', body),
}
