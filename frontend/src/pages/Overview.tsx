// «Обзор» — the first screen the jury sees: what the system does, its live state, three big buttons.
import { useEffect, useState } from 'react'
import { AlertTriangle, ArrowRight, Calculator, CheckCircle2, Cpu, Gavel, Languages, MessageSquare, Server, ShieldCheck, Sparkles, Thermometer, WifiOff, XCircle } from 'lucide-react'
import { motion } from 'motion/react'
import { agentApi, type AgentStatus } from '../agentV10'
import { tr } from '../i18n'

const JURY_KEY = 'bioreactor-agent-v10-jury'  // the same key the chat reads
// A status is never colour alone: each tone has its own icon next to the words.
const TONE_ICON = { ok: CheckCircle2, warn: AlertTriangle, bad: XCircle } as const

export default function Overview({ navigate }: { navigate: (page: string) => void }) {
  const [status, setStatus] = useState<AgentStatus | null>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    const load = () => agentApi.status().then(value => { setStatus(value); setFailed(false) }).catch(() => setFailed(true))
    load()
    const timer = setInterval(load, 20000)
    return () => clearInterval(timer)
  }, [])
  const openJury = () => { try { localStorage.setItem(JURY_KEY, '1') } catch { /* the chat opens in the farmer view */ } navigate('chat') }

  const gpu = status?.gpu
  const model = !status ? (failed ? tr('home.status.serverDown') : tr('home.status.loading'))
    : !status.llm_available ? tr('home.status.noModel')
    : gpu?.loaded ? tr('home.status.gpu', { v0: status.model, v1: gpu.gpu_percent ?? 100 }) : tr('home.status.modelReady', { v0: status.model })
  const version = status?.version
  const items = [
    { id: 'model', icon: Cpu, label: tr('home.status.model'), value: model, tone: status?.llm_available ? (gpu?.loaded ? 'ok' : 'warn') : 'bad' },
    { id: 'offline', icon: WifiOff, label: tr('home.status.network'), value: status?.offline === false ? tr('home.status.online') : tr('home.status.offline'), tone: status ? 'ok' : 'warn' },
    { id: 'server', icon: Server, label: tr('home.status.server'), tone: version ? (version.stale ? 'bad' : 'ok') : 'warn',
      value: version ? (version.stale ? tr('home.status.stale') : tr('home.status.version', { v0: version.commit, v1: (version.started_at ?? '').slice(11, 16) })) : '—' },
    { id: 'sensors', icon: Thermometer, label: tr('home.status.sensors'), value: tr('home.status.noSensors'), tone: 'warn' },
  ]
  const skills = [
    { icon: Languages, title: tr('home.skill.1.title'), text: tr('home.skill.1.text') },
    { icon: Calculator, title: tr('home.skill.2.title'), text: tr('home.skill.2.text') },
    { icon: ShieldCheck, title: tr('home.skill.3.title'), text: tr('home.skill.3.text') },
    { icon: Sparkles, title: tr('home.skill.4.title'), text: tr('home.skill.4.text') },
  ]
  return <div className="home">
    <motion.header className="home-hero" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .25, ease: [.23, 1, .32, 1] }}>
      <span className="home-eyebrow">{tr('home.eyebrow')}</span>
      <h1>{tr('home.title')}</h1>
      <p>{tr('home.lead')}</p>
      <div className="home-buttons">
        <button className="ds-button ds-button-primary home-button" data-testid="home-ask" onClick={() => navigate('chat')}><MessageSquare size={20} />{tr('home.ask')}</button>
        <button className="ds-button home-button" data-testid="home-calc" onClick={() => navigate('substrates')}><Calculator size={20} />{tr('home.calc')}</button>
        <button className="ds-button home-button" data-testid="home-jury" onClick={openJury}><Gavel size={20} />{tr('home.jury')}</button>
      </div>
    </motion.header>

    {/* one instrument panel: four gauges in one frame, not four cards */}
    <motion.section className="home-status-strip" aria-label={tr('home.status.title')} data-testid="home-status"
      initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .25, delay: .06, ease: [.23, 1, .32, 1] }}>
      {items.map(item => { const Tone = TONE_ICON[item.tone as keyof typeof TONE_ICON]; return <div key={item.id} className="home-status-item" data-tone={item.tone}>
        <span className="home-status-label"><item.icon size={18} aria-hidden="true" />{item.label}</span>
        <p className="home-status-value"><Tone size={18} aria-hidden="true" className="home-status-tone" /><strong data-testid={`home-status-${item.id}`}>{item.value}</strong></p>
      </div> })}
    </motion.section>

    {/* what the system does: a plain list, no card boxes */}
    <motion.section className="home-skills" aria-label={tr('home.skills')}
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: .25, delay: .12, ease: [.23, 1, .32, 1] }}>
      {skills.map(skill => <article key={skill.title} className="home-skill">
        <skill.icon size={22} aria-hidden="true" />
        <div><h2>{skill.title}</h2><p>{skill.text}</p></div>
      </article>)}
    </motion.section>

    <button className="home-more" onClick={() => navigate('science')}>{tr('home.more')} <ArrowRight size={16} /></button>
  </div>
}
