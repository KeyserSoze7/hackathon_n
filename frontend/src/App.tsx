import { useEffect, useState } from 'react'
import { Search, Receipt, BarChart3, Users, Wallet, MapPin, ChevronDown } from 'lucide-react'
import { api } from './data/api'
import { useAsync } from './lib/useAsync'
import { shortWard } from './lib/format'
import Logo from './components/Logo'
import Splash from './components/Splash'
import { Modal, ErrorBox } from './components/ui'
import Start from './screens/Start'
import RoadReceipt from './screens/RoadReceipt'
import City from './screens/City'
import Contractors from './screens/Contractors'
import NextRupee from './screens/NextRupee'

const SCREENS = ['start', 'receipt', 'city', 'contractors', 'nextrupee'] as const
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
      <header className="sticky top-0 z-40 bg-surface">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div className="flex min-w-0 max-w-full flex-wrap items-center gap-3">
            <a href="#start" aria-label="MARG·LEDGER home"><Logo /></a>
            <button onClick={() => setWardOpen(true)} aria-haspopup="dialog"
              className="flex min-h-[40px] min-w-0 max-w-full items-center gap-2 rounded-[8px] bg-hwgreen px-3.5 py-1.5 text-white hover:opacity-95">
              <MapPin size={16} strokeWidth={1.5} className="shrink-0" />
              <span className="mono truncate font-semibold tracking-wide">
                WARD {ward}<span className="hidden sm:inline">{current ? ` · ${shortWard(current.ward_name).toUpperCase()}` : ''}</span>
              </span>
              <ChevronDown size={14} strokeWidth={1.5} className="shrink-0" />
            </button>
          </div>
          <div role="group" aria-label="Language" className="flex items-center rounded-[14px] border border-hairline bg-concrete p-[4px]">
            {(['en', 'hi', 'mr'] as Lang[]).map((l) => (
              <button key={l} onClick={() => setLang(l)} aria-pressed={lang === l}
                className={`min-h-[38px] rounded-[10px] px-3 text-sm ${lang === l ? 'bg-hwyellow font-semibold' : 'font-medium text-muted hover:text-ink'}`}>
                {l === 'en' ? 'EN' : l === 'hi' ? 'हिन्दी' : 'मराठी'}
              </button>
            ))}
          </div>
        </div>

        <nav aria-label="Screens" className="border-t border-hairline">
          <ul className="mx-auto grid max-w-6xl grid-cols-5 gap-1 px-2 py-2 sm:flex sm:px-4">
            {NAV.map(({ id, icon: Icon, short, label }) => (
              <li key={id}>
                <a href={`#${id}`} onClick={(e) => { e.preventDefault(); go(id) }} aria-current={screen === id ? 'page' : undefined}
                  className={`flex min-h-[52px] flex-col items-center justify-center gap-1 rounded-[10px] px-2 py-1.5 text-center text-xs transition-colors sm:min-h-[46px] sm:flex-row sm:gap-2 sm:px-4 sm:text-sm ${screen === id ? 'bg-hwyellow font-semibold text-ink' : 'font-medium text-muted hover:bg-concrete hover:text-ink'}`}>
                  <Icon size={18} strokeWidth={1.5} />
                  <span className="sm:hidden">{short}</span>
                  <span className="hidden sm:inline">{label[lang]}</span>
                </a>
              </li>
            ))}
          </ul>
        </nav>
        <div className="kerb" aria-hidden />
      </header>

      <main className="mx-auto w-full min-w-0 max-w-6xl px-4 py-7 sm:py-9">
        {error && <div className="mb-6"><ErrorBox error={error} onRetry={reload} /></div>}
        {screen === 'start' && <Start wards={wards} ward={ward} onOpenRoad={openRoad} />}
        {screen === 'receipt' && <RoadReceipt roadId={roadId} onFind={() => go('start')} />}
        {screen === 'city' && <City wards={wards} ward={ward} onWard={setWard} onOpenRoad={openRoad} />}
        {screen === 'contractors' && <Contractors />}
        {screen === 'nextrupee' && <NextRupee wards={wards} ward={ward} onWard={setWard} onOpenRoad={openRoad} />}
      </main>

      {wardOpen && (
        <Modal title="Switch ward" onClose={() => setWardOpen(false)}>
          {!wards ? <p className="text-sm text-muted">Loading wards…</p> : (
            <div className="space-y-2">
              {wards.map((w) => (
                <button key={w.ward_code} onClick={() => { setWard(w.ward_code); setWardOpen(false) }} aria-pressed={w.ward_code === ward}
                  className={`flex min-h-[48px] w-full items-center justify-between gap-3 rounded-[8px] border px-4 text-left ${w.ward_code === ward ? 'border-ink bg-hwyellow' : 'border-hairline bg-concrete hover:border-ink'}`}>
                  <span className="font-semibold">{shortWard(w.ward_name)}</span>
                  <span className="mono font-semibold text-hwgreen">WARD {w.ward_code}</span>
                </button>
              ))}
            </div>
          )}
        </Modal>
      )}
    </div>
  )
}
