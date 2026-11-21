import { useEffect, useRef, useState } from 'react'

// Boot loading screen: the brand animation (assets/load_animation.*), shown once per browser session.
// It stays up until the data has loaded AND the logo lockup has formed (about 4.4 s into the
// animation), or until the animation ends. Skip closes it at any time.
const LOGO_FORMED_S = 4.6
const BG = '#F2F1EA' // the animation's own background, so the video edges are invisible
const KEY = 'marg-splash-seen'

export default function Splash({ ready }: { ready: boolean }) {
  const [show, setShow] = useState(() => sessionStorage.getItem(KEY) !== '1')
  const [leaving, setLeaving] = useState(false)
  const [formed, setFormed] = useState(false)
  const video = useRef<HTMLVideoElement>(null)
  const reduce = typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches

  const close = () => {
    sessionStorage.setItem(KEY, '1')
    setLeaving(true)
    window.setTimeout(() => setShow(false), 250)
  }

  // With reduced motion, show the still logo and close as soon as data is ready.
  useEffect(() => { if (reduce) setFormed(true) }, [reduce])
  // Safety net: if autoplay is blocked or the video stalls on a slow connection, never hold the app hostage.
  useEffect(() => {
    if (!show) return
    const t = window.setTimeout(() => setFormed(true), (LOGO_FORMED_S + 1.5) * 1000)
    video.current?.play().catch(() => setFormed(true))
    return () => window.clearTimeout(t)
  }, [show])
  useEffect(() => { if (show && ready && formed && !leaving) close() }, [show, ready, formed, leaving])

  if (!show) return null
  return (
    <div role="status" aria-label="Loading MARG" aria-live="polite"
      className="fixed inset-0 z-[60] flex items-center justify-center transition-opacity duration-200"
      style={{ background: BG, opacity: leaving ? 0 : 1 }}>
      {reduce ? (
        <img src="/brand/marg-logo.svg" alt="MARG, हर रुपये का हिसाब" className="h-auto w-[min(70vw,320px)]" />
      ) : (
        <video ref={video} autoPlay muted playsInline preload="auto" aria-hidden
          className="h-auto w-full max-w-[1280px]"
          onTimeUpdate={(e) => { if (e.currentTarget.currentTime >= LOGO_FORMED_S) setFormed(true) }}
          onEnded={() => setFormed(true)} onError={() => setFormed(true)}>
          <source src="/brand/load_animation.webm" type='video/webm; codecs="vp9, opus"' />
          <source src="/brand/load_animation.mp4" type="video/mp4" />
        </video>
      )}
      <button onClick={close} className="absolute bottom-6 right-6 min-h-[40px] rounded-[8px] border border-hairline bg-surface px-4 text-sm font-semibold hover:border-ink">
        Skip
      </button>
    </div>
  )
}
