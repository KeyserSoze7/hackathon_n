import { useEffect, useState } from 'react'
import { Search, Receipt, BarChart3, Users, Wallet, MapPin, ChevronDown, UserRound } from 'lucide-react'
import { api } from './data/api'
import { useAsync } from './lib/useAsync'
import { shortWard } from './lib/format'
import Logo from './components/Logo'
import Splash from './components/Splash'
import { DEMO } from './data/demo'
import { Modal, ErrorBox } from './components/ui'
import Start from './screens/Start'
import RoadReceipt from './screens/RoadReceipt'
import City from './screens/City'
import Contractors from './screens/Contractors'
import NextRupee from './screens/NextRupee'
import Me from './screens/Me'
import Admin from './screens/Admin'

const SCREENS = ['start', 'receipt', 'city', 'contractors', 'nextrupee', 'me', 'admin'] as const
type Screen = (typeof SCREENS)[number]
type Lang = 'en' | 'hi' | 'mr'

const NAV: { id: Screen; icon: typeof Search; short: string; label: Record<Lang, string> }[] = [
  { id: 'start', icon: Search, short: 'Find', label: { en: 'Find a road', hi: 'सड़क खोजें', mr: 'रस्ता शोधा' } },
  { id: 'receipt', icon: Receipt, short: 'Receipt', label: { en: 'Road receipt', hi: 'सड़क रसीद', mr: 'रस्ता पावती' } },
  { id: 'city', icon: BarChart3, short: 'City', label: { en: 'City audit', hi: 'शहर ऑडिट', mr: 'शहर ऑडिट' } },
  { id: 'contractors', icon: Users, short: 'Firms', label: { en: 'Contractors', hi: 'ठेकेदार', mr: 'कंत्राटदार' } },
  { id: 'nextrupee', icon: Wallet, short: 'Next ₹', label: { en: 'Next rupee', hi: 'अगला रुपया', mr: 'पुढचा रुपया' } },
]

const readHash = (): { screen: Screen; road: string | null } => {
  const [h, qs] = location.hash.slice(1).split('?')
  return { screen: (SCREENS as readonly string[]).includes(h) ? (h as Screen) : 'start', road: new URLSearchParams(qs).get('road') }
}

export default function App() {
  const [screen, setScreen] = useState<Screen>(() => readHash().screen)
  const [roadId, setRoadId] = useState(() => readHash().road ?? 'RD0220')
  const [ward, setWard] = useState('K/W')
  const [lang, setLang] = useState<Lang>('en')
  const [wardOpen, setWardOpen] = useState(false)
  const { data: wards, error, reload } = useAsync(api.wards, [])

  useEffect(() => {
    const on = () => { const h = readHash(); setScreen(h.screen); if (h.road) setRoadId(h.road); window.scrollTo({ top: 0 }) }
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])

  const go = (s: Screen) => { location.hash = s }
  const openRoad = (id: string) => { setRoadId(id); location.hash = `receipt?road=${encodeURIComponent(id)}` }
  const current = wards?.find((w) => w.ward_code === ward)

  return (
    <div className="min-h-full">
      <Splash ready={!!wards || !!error} />
      {DEMO && <p className="bg-ink px-4 py-2 text-center text-xs text-white">Demo version. Every figure is a saved snapshot of the live system; reports and replies you send stay in this browser only.</p>}
      <header className="sticky top-0 z-40 bg-surface">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-2 px-3 py-2 sm:gap-3 sm:px-4 sm:py-3">
          <div className="flex min-w-0 items-center gap-2 sm:gap-3">
            <a href="#start" aria-label="MARG home" className="shrink-0"><Logo /></a>
            <button onClick={() => setWardOpen(true)} aria-haspopup="dialog"
              className="flex min-h-[40px] min-w-0 items-center gap-1.5 rounded-[8px] bg-hwgreen px-2.5 py-1.5 text-white hover:opacity-95 sm:gap-2 sm:px-3.5">
              <MapPin size={16} strokeWidth={1.5} className="shrink-0" />
              <span className="mono truncate font-semibold tracking-wide">
                WARD {ward}<span className="hidden sm:inline">{current ? ` · ${shortWard(current.ward_name).toUpperCase()}` : ''}</span>
              </span>
              <ChevronDown size={14} strokeWidth={1.5} className="shrink-0" />
            </button>
          </div>
          <div className="flex shrink-0 items-center gap-1.5 sm:gap-2">
          <a href="#me" onClick={(e) => { e.preventDefault(); go('me') }} aria-label="My reports" aria-current={screen === 'me' ? 'page' : undefined}
            className={`grid h-[44px] w-[44px] place-items-center rounded-full border ${screen === 'me' ? 'border-ink bg-hwyellow' : 'border-hairline bg-concrete hover:border-ink'}`}>
            <UserRound size={20} strokeWidth={1.5} />
          </a>
          <div role="group" aria-label="Language" className="flex shrink-0 items-center rounded-[14px] border border-hairline bg-concrete p-[3px] sm:p-[4px]">
            {(['en', 'hi', 'mr'] as Lang[]).map((l) => (
              <button key={l} onClick={() => setLang(l)} aria-pressed={lang === l}
                className={`min-h-[38px] rounded-[10px] px-2.5 text-sm sm:px-3 ${lang === l ? 'bg-hwyellow font-semibold' : 'font-medium text-muted hover:text-ink'}`}>
                {l === 'en' ? 'EN' : l === 'hi' ? 'हिं' : 'मरा'}
              </button>
            ))}
          </div>
          </div>
        </div>

        {/* Desktop and tablet: navigation under the header. Phones use the bottom bar below. */}
        <nav aria-label="Screens" className="hidden border-t border-hairline sm:block">
          <ul className="mx-auto flex max-w-6xl gap-1 px-4 py-2">
            {NAV.map(({ id, icon: Icon, label }) => (
              <li key={id}>
                <a href={`#${id}`} onClick={(e) => { e.preventDefault(); go(id) }} aria-current={screen === id ? 'page' : undefined}
                  className={`flex min-h-[46px] items-center gap-2 rounded-[10px] px-4 text-sm transition-colors ${screen === id ? 'bg-hwyellow font-semibold text-ink' : 'font-medium text-muted hover:bg-concrete hover:text-ink'}`}>
                  <Icon size={18} strokeWidth={1.5} />{label[lang]}
                </a>
              </li>
            ))}
          </ul>
        </nav>
        <div className="kerb" aria-hidden />
      </header>

      <main className="mx-auto w-full min-w-0 max-w-6xl px-4 pb-28 pt-6 sm:py-9">
        {error && <div className="mb-6"><ErrorBox error={error} onRetry={reload} /></div>}
        {screen === 'start' && <Start wards={wards} ward={ward} onOpenRoad={openRoad} />}
        {screen === 'receipt' && <RoadReceipt roadId={roadId} onFind={() => go('start')} />}
        {screen === 'city' && <City wards={wards} ward={ward} onWard={setWard} onOpenRoad={openRoad} />}
        {screen === 'contractors' && <Contractors />}
        {screen === 'nextrupee' && <NextRupee wards={wards} ward={ward} onWard={setWard} onOpenRoad={openRoad} />}
        {screen === 'me' && <Me onFind={() => go('start')} onOpenRoad={openRoad} />}
        {screen === 'admin' && <Admin wards={wards} ward={ward} />}
      </main>

      {/* Phones: bottom navigation, thumb reachable, respects the home-indicator safe area. */}
      <nav aria-label="Screens" className="fixed inset-x-0 bottom-0 z-40 border-t border-hairline bg-surface pb-[env(safe-area-inset-bottom)] sm:hidden">
        <div className="kerb" aria-hidden />
        <ul className="grid grid-cols-5 gap-1 px-1.5 py-1.5">
          {NAV.map(({ id, icon: Icon, short }) => (
            <li key={id}>
              <a href={`#${id}`} onClick={(e) => { e.preventDefault(); go(id) }} aria-current={screen === id ? 'page' : undefined}
                className={`flex min-h-[56px] flex-col items-center justify-center gap-1 rounded-[12px] px-1 text-center text-[11px] leading-tight transition-colors ${screen === id ? 'bg-hwyellow font-bold text-ink' : 'font-medium text-muted active:bg-concrete'}`}>
                <Icon size={22} strokeWidth={1.5} />{short}
              </a>
            </li>
          ))}
        </ul>
      </nav>

      {wardOpen && (
        <Modal title="Switch ward" onClose={() => setWardOpen(false)}>
          {!wards ? <p className="text-sm text-muted">Loading wards…</p> : (
            <div className="grid grid-cols-2 gap-2">
              {wards.map((w) => (
                <button key={w.ward_code} onClick={() => { setWard(w.ward_code); setWardOpen(false) }} aria-pressed={w.ward_code === ward}
                  className={`flex min-h-[64px] flex-col items-start justify-center rounded-[12px] border-2 px-3 text-left ${w.ward_code === ward ? 'border-ink bg-hwyellow' : 'border-hairline bg-concrete hover:border-ink'}`}>
                  <span className="mono font-semibold text-hwgreen">WARD {w.ward_code}</span>
                  <span className="text-sm font-semibold leading-tight">{shortWard(w.ward_name)}</span>
                </button>
              ))}
            </div>
          )}
        </Modal>
      )}
    </div>
  )
}
