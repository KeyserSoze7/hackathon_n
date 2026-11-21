import { useEffect, type ReactNode } from 'react'
import { X, RotateCw } from 'lucide-react'
import { API_BASE } from '../data/api'

export const Skel = ({ className = '' }: { className?: string }) => <div className={`skeleton ${className}`} aria-hidden />

/** Evidence row IDs, work orders and complaint references. Mono is reserved for these. */
export const Id = ({ children }: { children: string }) => (
  <span className="mono whitespace-nowrap rounded-[6px] border border-hairline bg-concrete px-1.5 py-0.5">{children}</span>
)

/** Shown wherever the backend does not serve the data yet. */
export function Pending({ label, className = '' }: { label?: string; className?: string }) {
  return (
    <div className={`rounded-[8px] border border-dashed border-hairline bg-concrete p-4 text-sm text-muted ${className}`}>
      {label && <span className="font-semibold text-ink">{label}: </span>}Data coming in
    </div>
  )
}

export function ErrorBox({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-[12px] border-2 border-ink bg-surface p-4">
      <p className="text-sm">
        Could not reach the data service ({error.message}). Check you are on the same network as <span className="mono">{API_BASE}</span>.
      </p>
      {onRetry && (
        <button onClick={onRetry} className="flex min-h-[40px] items-center gap-2 rounded-[8px] bg-hwyellow px-4 text-sm font-bold hover:bg-hwyellow-strong">
          <RotateCw size={16} strokeWidth={1.5} /> Try again
        </button>
      )}
    </div>
  )
}

export function Modal({ title, onClose, children, footer }: { title: string; onClose: () => void; children: ReactNode; footer?: ReactNode }) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink/35 p-4 sm:items-center" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div role="dialog" aria-modal="true" aria-label={title} className="rise flex max-h-[88vh] w-full max-w-xl flex-col overflow-hidden rounded-[20px] border-2 border-ink bg-surface">
        <div className="flex items-center justify-between gap-3 border-b border-hairline px-5 py-4">
          <h2 className="text-lg font-bold">{title}</h2>
          <button onClick={onClose} aria-label="Close" className="grid h-9 w-9 place-items-center rounded-[8px] border border-hairline bg-concrete hover:border-ink"><X size={18} strokeWidth={1.5} /></button>
        </div>
        <div className="overflow-y-auto p-5">{children}</div>
        {footer && <div className="border-t border-hairline bg-concrete p-3">{footer}</div>}
      </div>
    </div>
  )
}

/** Primary action: the one yellow button per screen. */
export const Primary = ({ className = '', ...p }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
  <button {...p} className={`flex min-h-[48px] items-center justify-center gap-2 rounded-[8px] bg-hwyellow px-5 font-bold text-ink transition-colors hover:bg-hwyellow-strong active:translate-y-px disabled:opacity-50 ${className}`} />
)
