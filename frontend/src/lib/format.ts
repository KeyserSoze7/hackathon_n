/** Indian currency: Crores / Lakhs. */
export function inr(n: number): string {
  const a = Math.abs(n)
  if (a >= 1e7) return `₹${(n / 1e7).toFixed(2)} Cr`
  if (a >= 1e5) return `₹${(n / 1e5).toFixed(1)}L`
  return `₹${Math.round(n).toLocaleString('en-IN')}`
}
export const num = (n: number) => n.toLocaleString('en-IN')
export const pct = (x: number, d = 0) => `${(x * 100).toFixed(d)}%`
export function date(s: string): string {
  const d = new Date(s.replace(' ', 'T'))
  return Number.isNaN(d.getTime()) ? s : d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}
export const shortWard = (name?: string) => (name ?? '').split(',')[0]
export const cleanName = (n: string) => n.replace(' (synthetic)', '')

export const DETECTOR: Record<string, string> = {
  DLP_PAID_TWICE: 'Billed under warranty',
  RATE_INFLATION: 'Billed above rate card',
  OVERLAPPING_WORK_ORDER: 'Overlapping work order',
  RAIN_DAY_WORK: 'Work logged on a heavy-rain day',
  REPEAT_BILL_NO_COMPLAINT: 'Repeat bill with no new complaint',
}
export const REASON: Record<string, string> = {
  FLOOD_SPOT: 'Flood spot nearby', AMBULANCE_ROUTE: 'Hospital access road', HIGH_TRAFFIC: 'Heavy traffic',
  ACCIDENT_PRONE: 'Accidents from road defects', REPEAT_FAILURE: 'Repairs keep failing', UNDER_REPORTED_WARD: 'Ward under-reports',
  SCHOOL_ZONE: 'School zone', OPEN_COMPLAINTS: 'Open complaints', UNDER_DLP: 'Under warranty',
}
