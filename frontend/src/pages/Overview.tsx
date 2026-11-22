// «Обзор» — the first screen the jury sees. design-v3: the live reactor is the hero.
// Two concepts while the user chooses (?concept=a|b, src/concept.ts): A «Ночной чертёж», B «Живой процесс».
import { useEffect, useState, type CSSProperties } from 'react'
import { AlertTriangle, ArrowRight, Calculator, CheckCircle2, Cpu, Gavel, Languages, MessageSquare, Server, ShieldCheck, Sparkles, Thermometer, WifiOff, XCircle } from 'lucide-react'
import { agentApi, type AgentStatus } from '../agentV10'
import { tr } from '../i18n'
import { concept } from '../concept'
import type { Level } from '../reactorApi'
import { ReactorCutaway, ReactorProcess, sceneState, type SceneState } from '../overview/ReactorScene'
import { ArcGauge, BigNumber, LevelWord } from '../overview/Gauges'
import { DEMO_REACTOR, useReactorLive, type LiveReactor } from '../overview/useReactorLive'
import '../overview/overview.css'

const JURY_KEY = 'bioreactor-agent-v10-jury'  // the same key the chat reads
// A status is never colour alone: each tone has its own icon next to the words.
const TONE_ICON = { ok: CheckCircle2, warn: AlertTriangle, bad: XCircle } as const

function useAgentStatus() {
  const [status, setStatus] = useState<AgentStatus | null>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    const load = () => agentApi.status().then(value => { setStatus(value); setFailed(false) }).catch(() => setFailed(true))
    load()
    const timer = setInterval(load, 20000)
    return () => clearInterval(timer)
  }, [])
  return { status, failed }
}

function SystemLine({ status, failed, live }: { status: AgentStatus | null; failed: boolean; live: LiveReactor }) {
  const gpu = status?.gpu
  const model = !status ? (failed ? tr('home.status.serverDown') : tr('home.status.loading'))
    : !status.llm_available ? tr('home.status.noModel')
    : gpu?.loaded ? tr('home.status.gpu', { v0: status.model, v1: gpu.gpu_percent ?? 100 }) : tr('home.status.modelReady', { v0: status.model })
  const version = status?.version
  const r = live.status
  const sensors = !r ? tr('home.status.noSensors') : r.link.ok ? (r.source.kind === 'simulator' ? tr('ov.src.sim') : tr('ov.src.pi')) : tr('ov.noLink')
  const items = [
    { id: 'model', icon: Cpu, label: tr('home.status.model'), value: model, tone: status?.llm_available ? (gpu?.loaded ? 'ok' : 'warn') : 'bad' },
    { id: 'offline', icon: WifiOff, label: tr('home.status.network'), value: status?.offline === false ? tr('home.status.online') : tr('home.status.offline'), tone: status ? 'ok' : 'warn' },
    { id: 'server', icon: Server, label: tr('home.status.server'), tone: version ? (version.stale ? 'bad' : 'ok') : 'warn',
      value: version ? (version.stale ? tr('home.status.stale') : tr('home.status.version', { v0: version.commit, v1: (version.started_at ?? '').slice(11, 16) })) : '—' },
    { id: 'sensors', icon: Thermometer, label: tr('home.status.sensors'), value: sensors, tone: r?.link.ok ? 'ok' : 'warn' },
  ]
  return <section className="ov-system" aria-label={tr('home.status.title')} data-testid="home-status">
    {items.map(item => { const Tone = TONE_ICON[item.tone as keyof typeof TONE_ICON]; return <div key={item.id} data-tone={item.tone}>
      <item.icon size={16} aria-hidden="true" /><span>{item.label}:</span>
      <Tone size={16} aria-hidden="true" className="ov-tone" /><strong data-testid={`home-status-${item.id}`}>{item.value}</strong>
    </div> })}
  </section>
}

function LiveBadge({ live }: { live: LiveReactor }) {
  const r = live.status
  const on = Boolean(r?.link.ok)
  return <span className={`ov-live ${on ? '' : 'is-off'}`} data-testid="ov-live">
    <span className="ov-live-dot" aria-hidden="true" />
    {on ? `${tr('ov.live')} · ${r?.source.kind === 'simulator' ? tr('ov.src.sim') : tr('ov.src.pi')}` : tr('ov.noLink')}
  </span>
}

const methaneText = (live: LiveReactor) => {
  const m = live.methane
  return m?.methane_m3 ? tr('ov.methaneSub', { v0: m.methane_m3.low.toFixed(1), v1: m.methane_m3.high.toFixed(1), v2: DEMO_REACTOR.working_l,
    v3: m.days ? `${m.days.low}–${m.days.high}` : '25–35' }) : tr('ov.methaneWait')
}

function readouts(live: LiveReactor, s: SceneState) {
  const r = live.status
  const tempLevel: Level = r?.link.ok ? r.readings.temp_c.level : 'unknown'
  const gasLevel: Level = r?.link.ok ? r.readings.gas_in.level : 'unknown'
  const m = live.methane?.methane_m3
  const methane = m ? (m.low + m.high) / 2 : null
  return { tempLevel, gasLevel, methane, limits: r?.limits ?? null, temp: s.live ? s.temp : null, gasIn: s.live ? s.gasIn : null }
}

function Skills() {
  const skills = [
    { icon: Languages, title: tr('home.skill.1.title'), text: tr('home.skill.1.text') },
    { icon: Calculator, title: tr('home.skill.2.title'), text: tr('home.skill.2.text') },
    { icon: ShieldCheck, title: tr('home.skill.3.title'), text: tr('home.skill.3.text') },
    { icon: Sparkles, title: tr('home.skill.4.title'), text: tr('home.skill.4.text') },
  ]
  return <section className="ov-a-skills" aria-label={tr('home.skills')}>
    {skills.map(skill => <article key={skill.title}><skill.icon size={22} aria-hidden="true" /><h2>{skill.title}</h2><p>{skill.text}</p></article>)}
  </section>
}

function Buttons({ navigate }: { navigate: (page: string) => void }) {
  const openJury = () => { try { localStorage.setItem(JURY_KEY, '1') } catch { /* the chat opens in the farmer view */ } navigate('chat') }
  return <div className="ov-a-buttons">
    <button className="ds-button ds-button-primary home-button" data-testid="home-ask" onClick={() => navigate('chat')}><MessageSquare size={20} />{tr('home.ask')}</button>
    <button className="ds-button home-button" data-testid="home-calc" onClick={() => navigate('substrates')}><Calculator size={20} />{tr('home.calc')}</button>
    <button className="ds-button home-button" data-testid="home-jury" onClick={openJury}><Gavel size={20} />{tr('home.jury')}</button>
  </div>
}

function ConceptA({ navigate }: { navigate: (page: string) => void }) {
  const agent = useAgentStatus()
  const live = useReactorLive()
  const s = sceneState(live.status)
  const v = readouts(live, s)
  return <div className="ov-a" data-concept-view="a">
    <header className="ov-a-head ov-enter"><h1>{tr('home.title')}</h1><LiveBadge live={live} /></header>
    <section className="ov-a-sheet ov-enter">
      <figure className="ov-a-scene ov-enter-2"><ReactorCutaway s={s} /></figure>
      <div className="ov-a-side ov-enter-3">
        <div className="ov-a-instruments" aria-label={tr('ov.instruments')}>
          <ArcGauge testId="ov-temp" label={tr('ov.temp')} value={v.temp} min={0} max={60} unit="°C" level={v.tempLevel}
            band={v.limits ? [v.limits.temp_min, v.limits.temp_max] : [35, 38]} mark={v.limits?.temp_hard_max ?? 45} />
          <ArcGauge testId="ov-gas" label={tr('ov.gasIn')} value={v.gasIn} min={0} max={1023} unit={tr('ov.of1023')} level={v.gasLevel}
            digits={0} mark={v.limits?.gas_in_limit ?? 700} />
          <BigNumber label={tr('ov.methane')} level="ok" unit={tr('ov.m3')} value={v.methane == null ? '—' : `≈ ${v.methane.toFixed(1)}`} sub={methaneText(live)} />
        </div>
        <Buttons navigate={navigate} />
      </div>
    </section>
    <p className="ov-lead">{tr('home.lead')}</p>
    <SystemLine status={agent.status} failed={agent.failed} live={live} />
    <Skills />
    <button className="home-more" onClick={() => navigate('science')}>{tr('home.more')} <ArrowRight size={16} /></button>
  </div>
}

function ConceptB({ navigate }: { navigate: (page: string) => void }) {
  const agent = useAgentStatus()
  const live = useReactorLive()
  const s = sceneState(live.status)
  const v = readouts(live, s)
  return <div className="ov-b" data-concept-view="b" style={{ '--heat': s.heat.toFixed(3) } as CSSProperties}>
    <header className="ov-b-head ov-enter"><h1>{tr('home.title')}</h1><LiveBadge live={live} /></header>
    <figure className="ov-b-scene ov-enter-2"><ReactorProcess s={s} /></figure>
    <section className="ov-b-numbers ov-enter-3" aria-label={tr('ov.instruments')}>
      <figure className="ov-big" data-testid="ov-temp">
        <figcaption className="ov-gauge-label">{tr('ov.temp')}</figcaption>
        <div className="ov-big-readout"><span className="ov-big-number ds-num">{v.temp == null ? '—' : v.temp.toFixed(1)}</span><span className="ov-gauge-unit">°C</span></div>
        <p className="ov-big-sub"><LevelWord level={v.tempLevel} /> · {tr('ov.tempNorm', { v0: v.limits?.temp_min ?? 35, v1: v.limits?.temp_max ?? 38 })}</p>
      </figure>
      <figure className="ov-big" data-testid="ov-gas">
        <figcaption className="ov-gauge-label">{tr('ov.gasIn')}</figcaption>
        <div className="ov-big-readout"><span className="ov-big-number ds-num">{v.gasIn == null ? '—' : v.gasIn.toFixed(0)}</span><span className="ov-gauge-unit">{tr('ov.of1023')}</span></div>
        <p className="ov-big-sub"><LevelWord level={v.gasLevel} /> · {tr('ov.pumpAt', { v0: v.limits?.gas_in_limit ?? 700 })}</p>
      </figure>
      <figure className="ov-big">
        <figcaption className="ov-gauge-label">{tr('ov.methane')}</figcaption>
        <div className="ov-big-readout"><span className="ov-big-number ds-num">{v.methane == null ? '—' : `≈${v.methane.toFixed(1)}`}</span><span className="ov-gauge-unit">{tr('ov.m3')}</span></div>
        <p className="ov-big-sub">{methaneText(live)}</p>
      </figure>
    </section>
    <div className="ov-b-foot"><p className="ov-b-lead">{tr('home.lead')}</p><Buttons navigate={navigate} /></div>
    <SystemLine status={agent.status} failed={agent.failed} live={live} />
    <Skills />
    <button className="home-more" onClick={() => navigate('science')}>{tr('home.more')} <ArrowRight size={16} /></button>
  </div>
}

export default function Overview({ navigate }: { navigate: (page: string) => void }) {
  return concept() === 'b' ? <ConceptB navigate={navigate} /> : <ConceptA navigate={navigate} />
}
