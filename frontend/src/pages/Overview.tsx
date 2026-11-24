// «Обзор» — design-v3: near-black page, light «paper» and dark cards, one lime accent, section titles on a lime
// marker, mono labels and readings, pill buttons with ↗, our own line illustration of the live reactor.
// Read-only: nothing is switched from here. Statuses are a word + an icon, never colour alone.
import { useEffect, useState, type ReactNode } from 'react'
import { AlertTriangle, ArrowUpRight, CheckCircle2, HelpCircle, XCircle } from 'lucide-react'
import { agentApi, type AgentStatus } from '../agentV10'
import { tr } from '../i18n'
import type { Level } from '../reactorApi'
import { LineReactor } from '../overview/LineReactor'
import { IconChip, IconDrop, IconGas, IconLeak, IconRelay, IconThermo, Sparkle } from '../overview/LineIcons'
import { DEMO_REACTOR, sceneState, useReactorLive, type LiveReactor } from '../overview/useReactorLive'
import '../overview/overview.css'

const JURY_KEY = 'bioreactor-agent-v10-jury'  // the same key the chat reads
const LEVEL_ICON = { ok: CheckCircle2, warn: AlertTriangle, danger: XCircle, unknown: HelpCircle } as const
const TONE_LEVEL: Record<string, Level> = { ok: 'ok', warn: 'warn', bad: 'danger' }

export function LevelWord({ level }: { level: Level }) {
  const Icon = LEVEL_ICON[level]
  return <span className={`v3-level v3-level-${level}`}><Icon size={16} aria-hidden="true" />{tr(`ov.level.${level}`)}</span>
}

/** A section title on the lime marker. */
export function Marked({ children, as: Tag = 'h2', id }: { children: ReactNode; as?: 'h1' | 'h2'; id?: string }) {
  return <Tag className="v3-section-title" id={id}><span className="v3-mark">{children}</span></Tag>
}

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

function LiveBadge({ live }: { live: LiveReactor }) {
  const r = live.status
  const on = Boolean(r?.link.ok)
  return <span className={`v3-live ${on ? '' : 'is-off'}`} data-testid="ov-live">
    <span className="v3-live-dot" aria-hidden="true" />
    {on ? `${tr('ov.live')} · ${r?.source.kind === 'simulator' ? tr('ov.src.sim') : tr('ov.src.pi')}` : tr('ov.noLink')}
  </span>
}

function Metric({ tone, icon, label, value, unit, level, detail, testId }: {
  tone: 'paper' | 'dark'; icon: ReactNode; label: string; value: string; unit: string; level: Level; detail: string; testId: string
}) {
  return <article className={`v3-card v3-card-${tone} v3-metric`} data-testid={testId} data-level={level}>
    <header><span className="v3-label">{label}</span><span className="v3-metric-icon">{icon}</span></header>
    <p className="v3-metric-value"><span className="v3-num">{value}</span><span className="v3-unit">{unit}</span></p>
    <footer><LevelWord level={level} /><span className="v3-detail">{detail}</span></footer>
  </article>
}

function SystemCard({ status, failed, live }: { status: AgentStatus | null; failed: boolean; live: LiveReactor }) {
  const gpu = status?.gpu
  const model = !status ? (failed ? tr('home.status.serverDown') : tr('home.status.loading'))
    : !status.llm_available ? tr('home.status.noModel')
    : gpu?.loaded ? tr('home.status.gpu', { v0: status.model, v1: gpu.gpu_percent ?? 100 }) : tr('home.status.modelReady', { v0: status.model })
  const version = status?.version
  const r = live.status
  const sensors = !r ? tr('home.status.noSensors') : r.link.ok ? (r.source.kind === 'simulator' ? tr('ov.src.sim') : tr('ov.src.pi')) : tr('ov.noLink')
  const items = [
    { id: 'model', label: tr('home.status.model'), value: model, tone: status?.llm_available ? (gpu?.loaded ? 'ok' : 'warn') : 'bad' },
    { id: 'offline', label: tr('home.status.network'), value: status?.offline === false ? tr('home.status.online') : tr('home.status.offline'), tone: status ? 'ok' : 'warn' },
    { id: 'server', label: tr('home.status.server'), tone: version ? (version.stale ? 'bad' : 'ok') : 'warn',
      value: version ? (version.stale ? tr('home.status.stale') : tr('home.status.version', { v0: version.commit, v1: (version.started_at ?? '').slice(11, 16) })) : '—' },
    { id: 'sensors', label: tr('home.status.sensors'), value: sensors, tone: r?.link.ok ? 'ok' : 'warn' },
  ]
  return <article className="v3-card v3-card-dark v3-system" data-testid="home-status">
    <header><IconChip size={34} /><h3>{tr('home.status.title')}</h3></header>
    <dl>{items.map(item => { const Icon = LEVEL_ICON[TONE_LEVEL[item.tone]]; return <div key={item.id} data-tone={item.tone}>
      <dt className="v3-label">{item.label}</dt>
      <dd><Icon size={16} aria-hidden="true" className="v3-tone" /><strong data-testid={`home-status-${item.id}`}>{item.value}</strong></dd>
    </div> })}</dl>
  </article>
}

function SkillsCard() {
  const skills = [1, 2, 3, 4].map(n => ({ title: tr(`home.skill.${n}.title`), text: tr(`home.skill.${n}.text`) }))
  return <article className="v3-card v3-card-paper v3-skills" aria-label={tr('home.skills')}>
    <header><IconRelay size={34} /><h3>{tr('home.skills')}</h3></header>
    <ul>{skills.map(skill => <li key={skill.title}><Sparkle size={12} /><div><strong>{skill.title}</strong><p>{skill.text}</p></div></li>)}</ul>
  </article>
}

export default function Overview({ navigate }: { navigate: (page: string) => void }) {
  const agent = useAgentStatus()
  const live = useReactorLive()
  const s = sceneState(live.status)
  const r = live.status
  const level = (name: 'temp_c' | 'gas_in' | 'gas_out' | 'rh_pct'): Level => r?.link.ok ? r.readings[name].level : 'unknown'
  const value = (v: number | null, digits: number) => s.live && v != null ? v.toFixed(digits) : '—'
  const rh = s.live ? r?.readings.rh_pct.value ?? null : null
  const m = live.methane?.methane_m3
  const openJury = () => { try { localStorage.setItem(JURY_KEY, '1') } catch { /* the chat opens in the farmer view */ } navigate('chat') }

  return <div className="v3-overview">
    <section className="v3-hero">
      <div className="v3-hero-copy v3-enter">
        <Marked as="h2">{tr('app.1')}</Marked>
        <h1 className="v3-display">{tr('home.title')}</h1>
        <p className="v3-lead">{tr('home.lead')}</p>
        <div className="v3-buttons">
          <button className="v3-pill v3-pill-lime" data-testid="home-ask" onClick={() => navigate('chat')}>{tr('home.ask')}<ArrowUpRight size={18} aria-hidden="true" /></button>
          <button className="v3-pill" data-testid="home-calc" onClick={() => navigate('substrates')}>{tr('home.calc')}<ArrowUpRight size={18} aria-hidden="true" /></button>
          <button className="v3-pill" data-testid="home-jury" onClick={openJury}>{tr('home.jury')}<ArrowUpRight size={18} aria-hidden="true" /></button>
        </div>
        <LiveBadge live={live} />
      </div>
      <figure className="v3-card v3-card-paper v3-hero-art v3-enter-2">
        <LineReactor s={s} />
        <figcaption>
          <span className="v3-label">{tr('ov.methane')}</span>
          <span className="v3-hero-methane"><span className="v3-num">{m ? `≈ ${((m.low + m.high) / 2).toFixed(1)}` : '—'}</span> {tr('ov.m3')}</span>
          <span className="v3-detail">{m ? tr('ov.methaneSub', { v0: m.low.toFixed(1), v1: m.high.toFixed(1), v2: DEMO_REACTOR.working_l, v3: live.methane?.days ? `${live.methane.days.low}–${live.methane.days.high}` : '25–35' }) : tr('ov.methaneWait')}</span>
        </figcaption>
      </figure>
    </section>

    <section className="v3-section" aria-labelledby="v3-metrics">
      <div className="v3-section-head"><Marked id="v3-metrics">{tr('v3.metrics')}</Marked><LiveBadge live={live} /></div>
      <div className="v3-grid">
        <Metric tone="paper" testId="ov-temp" icon={<IconThermo size={36} />} label={tr('ov.temp')} value={value(s.temp, 1)} unit="°C" level={level('temp_c')}
          detail={tr('ov.tempNorm', { v0: r?.limits?.temp_min ?? 35, v1: r?.limits?.temp_max ?? 38 })} />
        <Metric tone="dark" testId="ov-gas" icon={<IconGas size={36} />} label={tr('ov.gasIn')} value={value(s.gasIn, 0)} unit={tr('ov.of1023')} level={level('gas_in')}
          detail={tr('ov.pumpAt', { v0: r?.limits?.gas_in_limit ?? 700 })} />
        <Metric tone="dark" testId="ov-leak" icon={<IconLeak size={36} />} label={tr('ov.gasOut')} value={value(s.gasOut, 0)} unit={tr('ov.of1023')} level={level('gas_out')}
          detail={tr('v3.leakAt', { v0: r?.limits?.gas_out_limit ?? 400 })} />
        <Metric tone="paper" testId="ov-rh" icon={<IconDrop size={36} />} label={tr('v3.rh')} value={rh == null ? '—' : rh.toFixed(1)} unit="%" level={level('rh_pct')}
          detail={tr('v3.rhWarn')} />
      </div>
    </section>

    <section className="v3-section v3-grid v3-grid-bottom">
      <SystemCard status={agent.status} failed={agent.failed} live={live} />
      <SkillsCard />
    </section>

    <button className="v3-pill v3-more" onClick={() => navigate('science')}>{tr('home.more')}<ArrowUpRight size={18} aria-hidden="true" /></button>
  </div>
}
