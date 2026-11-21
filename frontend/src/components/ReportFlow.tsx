import { useEffect, useMemo, useState } from 'react'
import { ArrowLeft, ArrowRight, Check, Crosshair, ImagePlus, MapPin, RotateCw, Trash2 } from 'lucide-react'
import { api, myReports } from '../data/api'
import type { CitizenReport } from '../data/types'
import { date } from '../lib/format'
import { Id, Modal, Pending, Primary } from './ui'
import Tracker from './Tracker'

// Citizen report workflow: what is wrong -> photo -> where -> review -> tracker.
// The backend currently takes text-level fields only, so the issue type, landmark and GPS are packed into the report text.
// Photo upload has no endpoint yet: the photo stays on the device and the step says so.

const KINDS = [
  { id: 'still_broken', title: 'Still broken', hint: 'A repair was done here but the problem is back, or it was never fixed.' },
  { id: 'new_issue', title: 'New problem', hint: 'Nothing has been repaired here before.' },
  { id: 'verified_fixed', title: 'Fixed and holding', hint: 'I checked the repair and it is holding up.' },
] as const

const ISSUES = [
  { id: 'pothole', label: 'Pothole' }, { id: 'waterlogging', label: 'Waterlogging' }, { id: 'open_manhole', label: 'Open or broken manhole' },
  { id: 'broken_paver', label: 'Broken paver blocks' }, { id: 'cave_in', label: 'Road cave-in' }, { id: 'choked_drain', label: 'Choked drain' },
  { id: 'other', label: 'Something else' },
]

const STEPS = ['What', 'Photo', 'Where', 'Review']

type Geo = { lat: number; lon: number; acc: number }
export interface ReportRoad { road_id: string; road_name: string; ward_code: string }

export default function ReportFlow({ road, locality, onClose, onOpenRoad }: { road: ReportRoad; locality?: string | null; onClose: () => void; onOpenRoad?: (id: string) => void }) {
  const [step, setStep] = useState(0)
  const [kind, setKind] = useState<(typeof KINDS)[number]['id'] | ''>('')
  const [issue, setIssue] = useState('')
  const [photo, setPhoto] = useState<File | null>(null)
  const [landmark, setLandmark] = useState('')
  const [note, setNote] = useState('')
  const [geo, setGeo] = useState<Geo | null>(null)
  const [geoState, setGeoState] = useState<'idle' | 'loading' | 'ok' | 'unavailable'>('idle')
  const [language, setLanguage] = useState<'en' | 'hi' | 'mr'>('en')
  const [phase, setPhase] = useState<'edit' | 'sending' | 'error' | 'done'>('edit')
  const [report, setReport] = useState<CitizenReport | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  const preview = useMemo(() => (photo ? URL.createObjectURL(photo) : null), [photo])
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview) }, [preview])

  const issueLabel = ISSUES.find((i) => i.id === issue)?.label ?? ''
  const kindTitle = KINDS.find((k) => k.id === kind)?.title ?? ''

  const locate = () => {
    if (!navigator.geolocation) return setGeoState('unavailable')
    setGeoState('loading')
    navigator.geolocation.getCurrentPosition(
      (p) => { setGeo({ lat: p.coords.latitude, lon: p.coords.longitude, acc: p.coords.accuracy }); setGeoState('ok') },
      () => setGeoState('unavailable'),
      { enableHighAccuracy: true, timeout: 10000 },
    )
  }

  const submit = async () => {
    if (!kind) return
    setPhase('sending')
    const lines = [`Issue: ${issueLabel}`]
    if (landmark.trim()) lines.push(`Landmark: ${landmark.trim()}`)
    if (geo) lines.push(`GPS: ${geo.lat.toFixed(5)}, ${geo.lon.toFixed(5)} (within ${Math.round(geo.acc)} m)`)
    if (note.trim()) lines.push(`Details: ${note.trim()}`)
    try {
      const r = await api.report({ kind, input_mode: 'text', text: lines.join('\n'), language, road_id: road.road_id, matched_locality: locality ?? null })
      myReports.add(r.id) // tie the report to this device until citizen accounts exist
      setReport(r); setPhase('done')
    } catch { setPhase('error') }
  }

  const refresh = async () => {
    if (!report) return
    setRefreshing(true)
    try { setReport(await api.reportStatus(report.id)) } catch { /* keep the last known tracker */ }
    setRefreshing(false)
  }

  const canNext = step === 0 ? !!kind && !!issue : true

  const footer = phase === 'done' ? (
    <div className="flex gap-2">
      <button onClick={() => { onClose(); location.hash = 'me' }} className="min-h-[48px] flex-1 rounded-[8px] border border-hairline bg-surface px-4 text-sm font-semibold hover:border-ink">My reports</button>
      {onOpenRoad && <button onClick={() => { onClose(); onOpenRoad(road.road_id) }} className="min-h-[48px] flex-1 rounded-[8px] border border-hairline bg-surface px-4 text-sm font-semibold hover:border-ink">Open road receipt</button>}
      <Primary onClick={onClose} className="flex-1">Done</Primary>
    </div>
  ) : (
    <div className="flex gap-2">
      <button onClick={() => (step === 0 ? onClose() : setStep(step - 1))} disabled={phase === 'sending'}
        className="flex min-h-[48px] items-center justify-center gap-2 rounded-[8px] border border-hairline bg-surface px-4 text-sm font-semibold hover:border-ink disabled:opacity-50">
        <ArrowLeft size={16} strokeWidth={1.5} /> {step === 0 ? 'Cancel' : 'Back'}
      </button>
      {step < 3 ? (
        <Primary onClick={() => setStep(step + 1)} disabled={!canNext} className="flex-1">
          {step === 1 && !photo ? 'Skip photo' : 'Next'} <ArrowRight size={16} strokeWidth={1.5} />
        </Primary>
      ) : (
        <Primary onClick={submit} disabled={phase === 'sending'} className="flex-1">{phase === 'sending' ? 'Sending…' : phase === 'error' ? 'Try again' : 'Send report'}</Primary>
      )}
    </div>
  )

  return (
    <Modal title={phase === 'done' ? 'Report sent' : 'Report a problem'} onClose={onClose} footer={footer}>
      {phase !== 'done' && (
        <div className="mb-5">
          <p className="mb-2 text-xs font-semibold text-muted">Step {step + 1} of 4: {STEPS[step]}</p>
          <div className="grid grid-cols-4 gap-1.5" aria-hidden>{STEPS.map((s, i) => <span key={s} className={`h-1.5 rounded-full ${i <= step ? 'bg-ink' : 'bg-hairline'}`} />)}</div>
        </div>
      )}

      {phase !== 'done' && (
        <div className="mb-5 rounded-[12px] border border-hairline bg-concrete p-4">
          <p className="text-xs text-muted">Reporting on</p>
          <p className="font-bold">{road.road_name}</p>
          <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted"><Id>{road.road_id}</Id><span>Ward {road.ward_code}</span>{locality && <span>{locality}</span>}</p>
        </div>
      )}

      {phase === 'edit' && step === 0 && (
        <div className="space-y-5">
          <fieldset className="space-y-3">
            <legend className="mb-1 font-bold">What is the situation?</legend>
            {KINDS.map((k) => (
              <label key={k.id} className={`flex cursor-pointer gap-3 rounded-[12px] border-2 p-4 ${kind === k.id ? 'border-ink bg-hwyellow/25' : 'border-hairline bg-surface hover:border-ink'}`}>
                <input type="radio" name="kind" value={k.id} checked={kind === k.id} onChange={() => setKind(k.id)} className="mt-1 h-4 w-4 accent-black" />
                <span><span className="block font-semibold">{k.title}</span><span className="text-sm text-muted">{k.hint}</span></span>
              </label>
            ))}
          </fieldset>
          <fieldset className="space-y-3">
            <legend className="mb-1 font-bold">What kind of problem?</legend>
            <div className="grid grid-cols-2 gap-2">
              {ISSUES.map((i) => (
                <label key={i.id} className={`flex min-h-[52px] cursor-pointer items-center rounded-[12px] border-2 px-3 py-2 text-sm font-medium ${issue === i.id ? 'border-ink bg-hwyellow/25' : 'border-hairline bg-surface hover:border-ink'}`}>
                  <input type="radio" name="issue" value={i.id} checked={issue === i.id} onChange={() => setIssue(i.id)} className="sr-only" />{i.label}
                </label>
              ))}
            </div>
          </fieldset>
        </div>
      )}

      {phase === 'edit' && step === 1 && (
        <div className="space-y-4">
          <h3 className="font-bold">Add a photo (optional)</h3>
          {preview ? (
            <div className="space-y-3 rounded-[12px] border border-hairline bg-concrete p-3">
              <img src={preview} alt="Your photo of the road" className="max-h-64 w-full rounded-[8px] object-contain" />
              <div className="flex items-center justify-between gap-3 text-sm">
                <span className="truncate text-muted">{photo?.name}</span>
                <button onClick={() => setPhoto(null)} className="flex min-h-[40px] shrink-0 items-center gap-2 rounded-[8px] border border-hairline bg-surface px-3 font-semibold hover:border-ink"><Trash2 size={16} strokeWidth={1.5} /> Remove</button>
              </div>
            </div>
          ) : (
            <label className="flex min-h-[140px] cursor-pointer flex-col items-center justify-center gap-2 rounded-[12px] border-2 border-dashed border-hairline bg-concrete p-6 text-center hover:border-ink">
              <ImagePlus size={32} strokeWidth={1.5} />
              <span className="font-semibold">Take a photo or choose one</span>
              <span className="text-sm text-muted">JPEG, PNG or WebP</span>
              <input type="file" accept="image/*" capture="environment" className="sr-only" onChange={(e) => setPhoto(e.target.files?.[0] ?? null)} />
            </label>
          )}
          <Pending label="Photo upload to the report" />
          <p className="text-sm text-muted">Until upload is ready, your photo stays on this device and is not sent with the report.</p>
        </div>
      )}

      {phase === 'edit' && step === 2 && (
        <div className="space-y-4">
          <h3 className="font-bold">Where exactly?</h3>
          <label className="block text-sm">
            <span className="font-medium">Landmark (optional)</span>
            <input value={landmark} onChange={(e) => setLandmark(e.target.value)} maxLength={150} placeholder="Opposite the bus depot"
              className="mt-1.5 min-h-[48px] w-full rounded-[8px] border border-hairline bg-surface px-3 placeholder:text-muted focus:border-ink focus:outline-none" />
          </label>
          <div className="space-y-2 rounded-[12px] border border-hairline bg-concrete p-4">
            <button onClick={locate} disabled={geoState === 'loading'} className="flex min-h-[48px] w-full items-center justify-center gap-2 rounded-[8px] border border-ink bg-surface font-semibold hover:bg-hwyellow/20 disabled:opacity-60">
              <Crosshair size={18} strokeWidth={1.5} /> {geoState === 'loading' ? 'Finding you…' : geo ? 'Update my location' : 'Use my location'}
            </button>
            {geo && <p className="flex items-center gap-2 text-sm"><MapPin size={16} strokeWidth={1.5} /> {geo.lat.toFixed(5)}, {geo.lon.toFixed(5)} (within {Math.round(geo.acc)} m)</p>}
            {geoState === 'unavailable' && <p className="text-sm text-muted">Location is not available here (it needs permission and a secure page). Add a landmark instead.</p>}
          </div>
          <label className="block text-sm">
            <span className="font-medium">Anything else? (optional)</span>
            <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} maxLength={500} placeholder="How long has it been like this?"
              className="mt-1.5 w-full rounded-[8px] border border-hairline bg-surface p-3 placeholder:text-muted focus:border-ink focus:outline-none" />
          </label>
        </div>
      )}

      {phase !== 'done' && step === 3 && (
        <div className="space-y-4">
          <h3 className="font-bold">Check and send</h3>
          <dl className="grid gap-3">
            <Row label="Situation" value={kindTitle} />
            <Row label="Problem" value={issueLabel} />
            <Row label="Photo" value={photo ? `${photo.name} (stays on this device)` : 'None'} />
            <Row label="Landmark" value={landmark.trim() || 'None'} />
            <Row label="Location" value={geo ? `${geo.lat.toFixed(5)}, ${geo.lon.toFixed(5)}` : 'Not shared'} />
            {note.trim() && <Row label="Details" value={note.trim()} />}
          </dl>
          <label className="block text-sm">
            <span className="font-medium">Language of this report</span>
            <select value={language} onChange={(e) => setLanguage(e.target.value as typeof language)} className="mt-1.5 min-h-[48px] w-full rounded-[8px] border border-hairline bg-surface px-3">
              <option value="en">English</option><option value="hi">हिन्दी</option><option value="mr">मराठी</option>
            </select>
          </label>
          {phase === 'error' && <p role="alert" className="rounded-[8px] border-2 border-ink p-3 text-sm">The report could not be sent. Check your connection and try again. Nothing was lost.</p>}
        </div>
      )}

      {phase === 'done' && report && (
        <div className="space-y-5">
          <div className="rounded-[12px] border-2 border-ink bg-hwyellow/25 p-4">
            <p className="flex items-center gap-2 font-bold"><Check size={20} strokeWidth={1.5} /> Report {report.id} received</p>
            <p className="mt-1 text-sm">Sent {date(report.created_at)} for {road.road_name}. Saved to My reports on this device.</p>
            {report.flag_id && <p className="mt-2 flex flex-wrap items-center gap-2 text-sm">Matched to flagged bill <Id>{report.flag_id.split(':').pop() ?? report.flag_id}</Id></p>}
          </div>
          <div className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <h3 className="font-bold">Where your report is now</h3>
              <button onClick={refresh} disabled={refreshing} className="flex min-h-[40px] items-center gap-2 rounded-[8px] border border-hairline bg-surface px-3 text-sm font-semibold hover:border-ink disabled:opacity-60">
                <RotateCw size={14} strokeWidth={1.5} className={refreshing ? 'animate-spin' : ''} /> Refresh
              </button>
            </div>
            <Tracker report={report} />
          </div>
        </div>
      )}
    </Modal>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return <div className="rounded-[12px] border border-hairline bg-concrete p-3"><dt className="text-xs text-muted">{label}</dt><dd className="font-semibold">{value}</dd></div>
}
