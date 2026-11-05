import { useEffect, useState } from 'react'
import { Activity, ArrowUpRight, Bot, ChartNoAxesCombined, ChevronRight, FlaskConical, LayoutDashboard, Menu, MessageSquare, Microscope, Presentation, Radio, Scale, Server, ShieldCheck, X } from 'lucide-react'
import { motion, MotionConfig } from 'motion/react'
import { api } from './api'
import { useQuery } from './hooks'
import Overview from './pages/Overview'
import Chat from './pages/Chat'
import Market from './pages/Market'
import Reactor from './pages/Reactor'
import Science from './pages/Science'
import System from './pages/System'
import Demo from './pages/Demo'
import { Badge } from './ui'
import { DisplayModeProvider, DisplayModeToggle } from './DisplayMode'
import SubstrateAdvisor from './pages/SubstrateAdvisorV81'
import './advisor.css'
import './clean.css'
import { canonicalRoute } from './routes'

const pages = [
 {id:'overview',title:'Обзор',en:'Overview',icon:LayoutDashboard},
 {id:'substrates',title:'Сырьё и смеси',en:'Substrates & Mixtures',icon:FlaskConical},
 {id:'chat',title:'AI Chat',en:'AI assistant',icon:MessageSquare},
 {id:'reactor',title:'Реактор',en:'Reactor',icon:Activity},
 {id:'market',title:'Рыночные цены',en:'Market prices',icon:ChartNoAxesCombined},
 {id:'science',title:'Источники и данные',en:'Sources & data',icon:Microscope},
 {id:'system',title:'Состояние системы',en:'System',icon:Server},
 {id:'demo',title:'Демонстрация',en:'Demo',icon:Presentation},
]
const route = () => canonicalRoute(window.location.hash)
export default function App() { return <DisplayModeProvider><Workspace /></DisplayModeProvider> }
function Workspace() {
  useEffect(() => { const canonical=canonicalRoute(window.location.hash); if(window.location.hash!=='#/'+canonical) window.history.replaceState(null,'','#/'+canonical) }, [])
  const [page, setPage] = useState(route); const [menuOpen, setMenuOpen] = useState(false)
  const health = useQuery('app-health', api.health)
  useEffect(() => { const timer = setInterval(health.refresh, 60000); return () => clearInterval(timer) }, [health.refresh])
  useEffect(() => {
    const changed = () => { const value=route(); if(window.location.hash!=='#/'+value) window.history.replaceState(null,'','#/'+value); setPage(value); setMenuOpen(false); window.scrollTo({ top: 0 }) }
    window.addEventListener('hashchange', changed)
    return () => window.removeEventListener('hashchange', changed)
  }, [])
  const navigate = (value: string) => { window.location.hash = '/' + value }
  const selected = pages.find(p => p.id === page)!
  const system = health.data?.status === 'ok' && !health.error
  return <MotionConfig reducedMotion="user">
    <a className="skip-link" href="#main-content" onClick={event => { event.preventDefault(); document.getElementById('main-content')?.focus() }}>К содержимому</a>
    <div className="app-shell">
      <aside className={`sidebar ${menuOpen ? 'sidebar-open' : ''}`}>
        <a className="brand" href="#/overview" aria-label="BioReactor AI, обзор"><div className="brand-symbol"><FlaskConical size={25} /></div><div><strong>BioReactor<span>AI</span></strong><small>BIOGAS ASSISTANT</small></div></a>
        <div className="workspace-pill"><span className="status-dot" /><span>Моя установка</span><span className="workspace-code">KZ</span></div>
        <span className="nav-caption">РАБОЧАЯ СРЕДА</span>
        <nav aria-label="Основная навигация">{pages.filter(item => !['system', 'demo'].includes(item.id)).map(item => <button key={item.id} className={`nav-item ${page === item.id ? 'active' : ''}`} aria-current={page === item.id ? 'page' : undefined} onClick={() => navigate(item.id)}><item.icon size={19} /><span>{item.title}</span>{page === item.id && <span className="nav-indicator" />}</button>)}</nav>
        <span className="nav-caption nav-caption-system">СИСТЕМА</span>
        <nav aria-label="Диагностика"><button className={`nav-item ${page === 'system' ? 'active' : ''}`} aria-current={page === 'system' ? 'page' : undefined} onClick={() => navigate('system')}><Server size={19} /><span>Состояние системы</span><span className={`nav-state ${system ? 'connected' : ''}`} /></button></nav>
        <div className="sidebar-bottom"><div className="local-card"><div><ShieldCheck size={15} /><strong>Локальная среда</strong></div><p>Научные данные остаются<br />под вашим контролем</p><span>v8.3 <span>•</span> Research prototype</span></div></div>
      </aside>
      {menuOpen && <button className="menu-scrim" aria-label="Закрыть навигацию" onClick={() => setMenuOpen(false)} />}
      <div className="main-shell">
        <header className="topbar">
          <button className="menu-button icon-button" aria-label={menuOpen ? 'Закрыть меню' : 'Открыть меню'} onClick={() => setMenuOpen(value => !value)}>{menuOpen ? <X size={20} /> : <Menu size={20} />}</button>
          <div className="breadcrumb"><span>Workspace</span><ChevronRight size={13} /><strong>{selected.en}</strong></div>
          <div className="topbar-right"><DisplayModeToggle /><span className="topbar-region">Караганда, Казахстан</span><Badge tone={system ? 'green' : health.error ? 'red' : 'muted'}>{system ? 'Подключено' : health.error ? 'Сервер недоступен' : 'Подключение…'}</Badge><button className="header-system-button" aria-label="Диагностика компонентов" onClick={() => navigate('system')}><Radio size={17} /></button><div className="user-mark" title="Локальный оператор">BR</div></div>
        </header>
        <main id="main-content" tabIndex={-1}>
          <motion.div key={page} className="page-content" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .18 }}>
            {page === 'overview' && <Overview navigate={navigate} />}{page === 'chat' && <Chat />}{page === 'substrates' && <SubstrateAdvisor mixture />}{page === 'market' && <Market onChange={health.refresh} />}{page === 'reactor' && <Reactor />}{page === 'science' && <Science />}{page === 'system' && <System />}{page === 'demo' && <Demo navigate={navigate} />}
          </motion.div>
          <footer className="app-footer"><span>BioReactor AI <span className="footer-divider">/</span> Локальный ассистент по биогазу</span><span><ShieldCheck size={12} />Проверяемые данные · ответственные выводы</span></footer>
        </main>
      </div>
    </div>
  </MotionConfig>
}
