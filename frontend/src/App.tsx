import { useEffect, useState } from 'react'
import { Activity, ArrowUpRight, Bot, ChartNoAxesCombined, ChevronRight, FlaskConical, LayoutDashboard, Menu, MessageSquare, Microscope, Presentation, Radio, Scale, Server, ShieldCheck, X } from 'lucide-react'
import { motion, MotionConfig } from 'motion/react'
import { api } from './api'
import { useQuery } from './hooks'
import Overview from './pages/Overview'
import Chat from './pages/Chat'
import AgentChat from './pages/AgentChat'
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
import { I18nProvider, localized, tr, useI18n } from './i18n'
import { LanguageSwitch } from './LanguageSwitch'

const pages = localized(() => ([
 {id:'overview',title:tr('app.1'),en:'Overview',icon:LayoutDashboard},
 {id:'substrates',title:tr('app.2'),en:'Substrates & Mixtures',icon:FlaskConical},
 {id:'chat',title:tr('app.chat'),en:'AI assistant',icon:MessageSquare},
 {id:'chat-v9',title:tr('app.3'),en:'AI assistant v9 (legacy)',icon:MessageSquare},
 {id:'reactor',title:tr('app.4'),en:'Reactor',icon:Activity},
 {id:'market',title:tr('app.5'),en:'Market prices',icon:ChartNoAxesCombined},
 {id:'science',title:tr('app.6'),en:'Sources & data',icon:Microscope},
 {id:'system',title:tr('app.7'),en:'System',icon:Server},
 {id:'demo',title:tr('app.8'),en:'Demo',icon:Presentation},
]))
const route = () => canonicalRoute(window.location.hash)
export default function App() { return <I18nProvider><DisplayModeProvider><Workspace /></DisplayModeProvider></I18nProvider> }
function Workspace() {
  useI18n()  // a language switch re-renders the whole page at once

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
    <a className="skip-link" href="#main-content" onClick={event => { event.preventDefault(); document.getElementById('main-content')?.focus() }}>{tr('app.9')}</a>
    <div className="app-shell">
      <aside className={`sidebar ${menuOpen ? 'sidebar-open' : ''}`}>
        <a className="brand" href="#/overview" aria-label={tr('app.10')}><div className="brand-symbol"><FlaskConical size={25} /></div><div><strong>BioReactor<span>AI</span></strong><small>{tr('app.tagline')}</small></div></a>
        <div className="workspace-pill"><span className="status-dot" /><span>{tr('app.11')}</span><span className="workspace-code">KZ</span></div>
        <span className="nav-caption">{tr('app.12')}</span>
        <nav aria-label={tr('app.13')}>{pages.filter(item => !['system', 'demo', 'chat-v9'].includes(item.id)).map(item => <button key={item.id} className={`nav-item ${page === item.id ? 'active' : ''}`} aria-current={page === item.id ? 'page' : undefined} onClick={() => navigate(item.id)}><item.icon size={19} /><span>{item.title}</span>{page === item.id && <span className="nav-indicator" />}</button>)}</nav>
        <span className="nav-caption nav-caption-system">{tr('app.14')}</span>
        <nav aria-label={tr('app.15')}><button className={`nav-item ${page === 'system' ? 'active' : ''}`} aria-current={page === 'system' ? 'page' : undefined} onClick={() => navigate('system')}><Server size={19} /><span>{tr('app.7')}</span><span className={`nav-state ${system ? 'connected' : ''}`} /></button></nav>
        <div className="sidebar-bottom"><div className="local-card"><div><ShieldCheck size={15} /><strong>{tr('app.16')}</strong></div><p>{tr('app.17')}<br />{tr('app.18')}</p><span>v8.3 <span>•</span> {tr('app.prototype')}</span></div></div>
      </aside>
      {menuOpen && <button className="menu-scrim" aria-label={tr('app.19')} onClick={() => setMenuOpen(false)} />}
      <div className="main-shell">
        <header className="topbar">
          <button className="menu-button icon-button" aria-label={menuOpen ? tr('app.20') : tr('app.21')} onClick={() => setMenuOpen(value => !value)}>{menuOpen ? <X size={20} /> : <Menu size={20} />}</button>
          <div className="breadcrumb"><span>{tr('app.workspace')}</span><ChevronRight size={13} /><strong>{selected.title}</strong></div>
          <div className="topbar-right"><LanguageSwitch /><DisplayModeToggle /><span className="topbar-region">{tr('app.22')}</span><Badge tone={system ? 'green' : health.error ? 'red' : 'muted'}>{system ? tr('app.23') : health.error ? tr('app.24') : tr('app.25')}</Badge><button className="header-system-button" aria-label={tr('app.26')} onClick={() => navigate('system')}><Radio size={17} /></button><div className="user-mark" title={tr('app.27')}>BR</div></div>
        </header>
        <main id="main-content" tabIndex={-1}>
          <motion.div key={page} className="page-content" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .18 }}>
            {page === 'overview' && <Overview navigate={navigate} />}{page === 'chat' && <AgentChat />}{page === 'chat-v9' && <Chat />}{page === 'substrates' && <SubstrateAdvisor mixture />}{page === 'market' && <Market onChange={health.refresh} />}{page === 'reactor' && <Reactor />}{page === 'science' && <Science />}{page === 'system' && <System />}{page === 'demo' && <Demo navigate={navigate} />}
          </motion.div>
          <footer className="app-footer"><span>BioReactor AI <span className="footer-divider">/</span> {tr('app.28')}</span><span><ShieldCheck size={12} />{tr('app.29')}</span></footer>
        </main>
      </div>
    </div>
  </MotionConfig>
}
