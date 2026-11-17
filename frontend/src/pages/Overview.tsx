// «Обзор» — the first screen the jury sees: what the system does, its live state, three big buttons.
import { useEffect, useState } from 'react'
import { ArrowRight, Calculator, Cpu, Gavel, Languages, MessageSquare, Server, ShieldCheck, Sparkles, Thermometer, WifiOff } from 'lucide-react'
import { motion } from 'motion/react'
import { agentApi, type AgentStatus } from '../agentV10'
import { tr } from '../i18n'

const JURY_KEY = 'bioreactor-agent-v10-jury'  // the same key the chat reads

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
    <motion.header className="home-hero" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .3 }}>
      <span className="home-eyebrow">{tr('home.eyebrow')}</span>
      <h1>{tr('home.title')}</h1>
      <p>{tr('home.lead')}</p>
      <div className="home-buttons">
        <button className="ds-button ds-button-primary home-button" data-testid="home-ask" onClick={() => navigate('chat')}><MessageSquare size={20} />{tr('home.ask')}</button>
        <button className="ds-button home-button" data-testid="home-calc" onClick={() => navigate('substrates')}><Calculator size={20} />{tr('home.calc')}</button>
        <button className="ds-button home-button" data-testid="home-jury" onClick={openJury}><Gavel size={20} />{tr('home.jury')}</button>
      </div>
    </motion.header>

    <section className="home-status-strip" aria-label={tr('home.status.title')} data-testid="home-status">
      {items.map((item, index) => <motion.div key={item.id} className="home-status-item" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .25, delay: .1 + index * .05 }}>
        <item.icon size={20} />
        <div><span>{item.label}</span><strong className="ds-status" data-tone={item.tone} data-testid={`home-status-${item.id}`}>{item.value}</strong></div>
      </motion.div>)}
    </section>

    <section className="home-skills" aria-label={tr('home.skills')}>
      {skills.map((skill, index) => <motion.article key={skill.title} className="home-skill ds-card" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .25, delay: .2 + index * .06 }}>
        <skill.icon size={24} />
        <h2>{skill.title}</h2>
        <p>{skill.text}</p>
      </motion.article>)}
    </section>

    <button className="home-more" onClick={() => navigate('science')}>{tr('home.more')} <ArrowRight size={16} /></button>
  </div>
}
