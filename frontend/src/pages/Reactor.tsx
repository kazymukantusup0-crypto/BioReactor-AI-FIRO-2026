// «Реактор»: live sensors and manual relays. Chain: Arduino -> USB -> Raspberry Pi -> network -> this page.
// The page only shows what the Pi reports; every command is a person's button + a confirmation. Automatic protection
// (Arduino first, then the Pi) only switches relays OFF. The AI agent reads the same data and never presses buttons.
import { useCallback, useEffect, useRef, useState } from 'react'
import { AlertOctagon, AlertTriangle, ArrowRight, Bot, Cable, CheckCircle2, Cpu, Droplets, Fan, Flame, Gauge, Gavel, HelpCircle, Laptop, LayoutDashboard, Network, PlugZap, Power, RadioTower, RefreshCw, ShieldAlert, Thermometer, Wind, Wrench, XCircle } from 'lucide-react'
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { reactorApi, RELAYS, SENSORS, type CheckResult, type HistoryPoint, type JournalItem, type Level, type ReactorStatus, type RelayName, type SensorName, type SimulatorSwitch, type Thresholds } from '../reactorApi'
import { tr } from '../i18n'
import '../reactor.css'

const JURY_KEY = 'bioreactor-reactor-jury'
const ICONS: Record<SensorName, typeof Thermometer> = { temp_c: Thermometer, rh_pct: Droplets, gas_in: Wind, gas_out: ShieldAlert, p_kpa: Gauge }
const RELAY_ICONS: Record<RelayName, typeof Flame> = { heat: Flame, cool: Fan, pump: Power }
const DIGITS: Record<SensorName, number> = { temp_c: 1, rh_pct: 1, gas_in: 0, gas_out: 0, p_kpa: 2 }

function readStorage(key: string): string | null { try { return localStorage.getItem(key) } catch { return null } }
function writeStorage(key: string, value: string) { try { localStorage.setItem(key, value) } catch { /* optional preference */ } }

export function formatValue(name: SensorName, value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return value.toFixed(DIGITS[name])
}

export function duration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds))
  if (s < 60) return tr('rx.dur.s', { s })
  if (s < 3600) return tr('rx.dur.m', { m: Math.floor(s / 60), s: s % 60 })
  return tr('rx.dur.h', { h: Math.floor(s / 3600), m: Math.floor((s % 3600) / 60) })
}

const unit = (name: SensorName) => tr(`rx.unit.${name}`)
const levelText = (level: Level) => tr(`rx.level.${level}`)

function LevelChip({ level }: { level: Level }) {
  const Icon = level === 'ok' ? CheckCircle2 : level === 'warn' ? AlertTriangle : level === 'danger' ? AlertOctagon : HelpCircle
  return <span className={`rx-level rx-level-${level}`}><Icon size={15} aria-hidden="true" />{levelText(level)}</span>
}

// ---------------------------------------------------------------- source and link
export function SourceBadge({ status, big = false }: { status: ReactorStatus | null; big?: boolean }) {
  if (!status) return <span className={`rx-source rx-source-unknown ${big ? 'rx-big' : ''}`} data-testid="rx-source"><Cable size={16} />{tr('rx.source.unknown')}</span>
  const simulator = status.source.kind === 'simulator'
  return <span className={`rx-source ${simulator ? 'rx-source-sim' : 'rx-source-pi'} ${big ? 'rx-big' : ''}`} data-testid="rx-source">
    {simulator ? <Cpu size={16} /> : <RadioTower size={16} />}
    {simulator ? tr('rx.source.sim')
      // a real Pi started with --simulate: the network is real, the sensors are not — say so
      : status.source.arduino_port === 'virtual' ? tr('rx.source.piVirtual', { address: status.source.address ?? '?' })
      : tr('rx.source.pi', { address: status.source.address ?? '?' })}
  </span>
}

function LinkBanner({ status, serverDown }: { status: ReactorStatus | null; serverDown: boolean }) {
  if (!serverDown && status?.link.ok) return null
  const level = serverDown ? 'server' : status?.link.level === 'arduino' ? 'arduino' : 'pi'
  return <section className="rx-nolink" role="alert" data-testid="rx-nolink">
    <PlugZap size={34} aria-hidden="true" />
    <div><h2>{tr(`rx.nolink.${level}`)}</h2><p>{tr(`rx.nolink.${level}Text`)}</p>
      {status?.link.error && !serverDown && <p className="rx-mono">{status.link.error}</p>}</div>
  </section>
}

function CheckButton() {
  const [result, setResult] = useState<CheckResult | null>(null)
  const [busy, setBusy] = useState(false)
  const run = async () => {
    setBusy(true)
    try { setResult(await reactorApi.check()) } catch (error) { setResult({ ok: false, url: '', mode: '', latency_ms: 0, error: String((error as Error).message ?? error) }) } finally { setBusy(false) }
  }
  return <div className="rx-check">
    <button className="ds-button" onClick={run} disabled={busy} data-testid="rx-check"><RefreshCw size={16} className={busy ? 'spin' : ''} />{tr('rx.check')}</button>
    {result && <span className={`rx-check-result ${result.ok ? 'is-ok' : 'is-bad'}`} role="status" data-testid="rx-check-result">
      {result.ok ? tr('rx.checkOk', { ms: result.latency_ms, port: result.port ?? '—', arduino: result.arduino_ok ? tr('rx.yes') : tr('rx.no') })
        : tr('rx.checkFail', { error: result.error ?? '' })}
    </span>}
  </div>
}

// ---------------------------------------------------------------- readings
function readingNote(name: SensorName, status: ReactorStatus): string {
  const th = status.thresholds
  if (!th) return ''
  if (name === 'temp_c') return tr('rx.note.temp', { target: th.temp_c.target, low: th.temp_c.warn_low, high: th.temp_c.warn_high, over: th.overheat_c })
  if (name === 'rh_pct') return tr('rx.note.rh', { high: th.rh_pct.warn_high })
  if (name === 'gas_in') return tr('rx.note.gasIn')
  if (name === 'gas_out') return tr('rx.note.gasOut', { leak: th.gas_out_raw.leak })
  return tr('rx.note.pressure', { pump: th.pressure_kpa.pump_warn, danger: th.pressure_kpa.danger })
}

function ReadingCard({ name, status, big }: { name: SensorName; status: ReactorStatus; big?: boolean }) {
  const reading = status.readings[name]
  const Icon = ICONS[name]
  const stale = !status.link.ok
  return <article className={`rx-reading ds-card rx-tone-${reading.level} ${big ? 'rx-reading-big' : ''}`} data-testid={`rx-reading-${name}`}>
    <span className="rx-reading-title"><Icon size={18} aria-hidden="true" />{tr(`rx.sensor.${name}`)}</span>
    <strong className="rx-reading-value">{formatValue(name, reading.value)}<small>{unit(name)}</small></strong>
    <LevelChip level={reading.level} />
    {name === 'p_kpa' && reading.fill_share !== null && reading.fill_share !== undefined && status.thresholds &&
      <div className="rx-fill" aria-label={tr('rx.fillLabel')}>
        <div className="rx-fill-track"><div className={`rx-fill-bar rx-tone-${reading.level}`} style={{ width: `${Math.round(reading.fill_share * 100)}%` }} />
          <span className="rx-fill-mark" style={{ left: `${(status.thresholds.pressure_kpa.pump_warn / status.thresholds.pressure_kpa.scale_max) * 100}%` }} /></div>
        <span>{reading.level === 'ok' ? tr('rx.fill.ok') : tr('rx.fill.pump')}</span>
      </div>}
    {!big && <span className="rx-reading-note">{readingNote(name, status)}</span>}
    {stale && reading.last !== null && <span className="rx-reading-stale">{tr('rx.lastKnown', { value: formatValue(name, reading.last), unit: unit(name) })}</span>}
  </article>
}

// ---------------------------------------------------------------- charts (one small chart per measure: never two scales)
function thresholdLines(name: SensorName, th: Thresholds | null): { y: number; tone: 'warn' | 'danger' | 'target'; label: string }[] {
  if (!th) return []
  if (name === 'temp_c') return [{ y: th.temp_c.target, tone: 'target', label: tr('rx.line.target') }, { y: th.temp_c.warn_low, tone: 'warn', label: '' }, { y: th.overheat_c, tone: 'danger', label: tr('rx.line.overheat') }]
  if (name === 'rh_pct') return [{ y: th.rh_pct.warn_high, tone: 'warn', label: '' }]
  if (name === 'gas_in') return [{ y: th.gas_in_raw.warn_low, tone: 'warn', label: '' }]
  if (name === 'gas_out') return [{ y: th.gas_out_raw.warn, tone: 'warn', label: '' }, { y: th.gas_out_raw.leak, tone: 'danger', label: tr('rx.line.leak') }]
  return [{ y: th.pressure_kpa.pump_warn, tone: 'warn', label: tr('rx.line.pump') }, { y: th.pressure_kpa.danger, tone: 'danger', label: '' }]
}
const LINE_COLORS = { warn: '#e9bd6c', danger: '#f3958a', target: '#8cc4ee' }
const clock = (t: number) => new Date(t * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })

function SensorChart({ name, points, th }: { name: SensorName; points: HistoryPoint[]; th: Thresholds | null }) {
  const data = points.map(p => ({ t: p.t, v: p[name] }))
  return <figure className="rx-chart ds-card" data-testid={`rx-chart-${name}`}>
    <figcaption>{tr(`rx.sensor.${name}`)}<span>, {unit(name)}</span></figcaption>
    {data.length < 2 ? <p className="ds-muted rx-chart-empty">{tr('rx.chartEmpty')}</p> :
      <div className="rx-chart-box"><ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 10, right: 12, bottom: 0, left: -12 }}>
          <CartesianGrid stroke="#24333b" strokeDasharray="3 5" vertical={false} />
          <XAxis dataKey="t" type="number" domain={['dataMin', 'dataMax']} tickFormatter={v => clock(Number(v)).slice(0, 5)} axisLine={false} tickLine={false} tick={{ fill: '#8fa6aa', fontSize: 13 }} minTickGap={40} />
          <YAxis domain={['auto', 'auto']} axisLine={false} tickLine={false} tick={{ fill: '#8fa6aa', fontSize: 13 }} width={52} tickFormatter={v => Number(v).toFixed(DIGITS[name] === 2 ? 1 : 0)} />
          {thresholdLines(name, th).map(line => <ReferenceLine key={`${line.tone}${line.y}`} y={line.y} stroke={LINE_COLORS[line.tone]} strokeDasharray={line.tone === 'target' ? '2 4' : '6 4'} ifOverflow="extendDomain"
            label={line.label ? { value: line.label, position: 'insideTopRight', fill: '#a9bdbf', fontSize: 13 } : undefined} />)}
          <Tooltip contentStyle={{ background: '#152329', border: '1px solid #36525a', borderRadius: 10, color: '#f0f7f5' }} labelFormatter={v => clock(Number(v))}
            formatter={value => [`${formatValue(name, value as number | null)} ${unit(name)}`, tr(`rx.sensor.${name}`)]} />
          <Line type="monotone" dataKey="v" stroke="#55d6af" strokeWidth={2} dot={false} activeDot={{ r: 5, stroke: '#111c22', strokeWidth: 2 }} isAnimationActive={false} connectNulls={false} />
        </LineChart>
      </ResponsiveContainer></div>}
  </figure>
}

function Charts({ status }: { status: ReactorStatus }) {
  const [window, setWindow] = useState<600 | 3600>(600)
  const [points, setPoints] = useState<HistoryPoint[]>([])
  const [live, setLive] = useState(true)
  useEffect(() => {
    const controller = new AbortController()
    const load = () => reactorApi.history(window, controller.signal).then(r => { setPoints(r.points); setLive(r.live) }).catch(() => setLive(false))
    load()
    const timer = setInterval(load, 5000)
    return () => { controller.abort(); clearInterval(timer) }
  }, [window])
  return <section className="rx-section" aria-labelledby="rx-charts-title">
    <div className="rx-section-head"><h2 id="rx-charts-title">{tr('rx.charts')}</h2>
      <div className="rx-segmented" role="group" aria-label={tr('rx.window')}>
        <button aria-pressed={window === 600} onClick={() => setWindow(600)}>{tr('rx.window10')}</button>
        <button aria-pressed={window === 3600} onClick={() => setWindow(3600)}>{tr('rx.window60')}</button>
      </div></div>
    {!live && <p className="ds-muted">{tr('rx.chartsStale')}</p>}
    <div className="rx-charts">{SENSORS.map(name => <SensorChart key={name} name={name} points={points} th={status.thresholds} />)}</div>
    <details className="ds-collapse rx-table-view"><summary>{tr('rx.tableView')}</summary>
      <div className="rx-table-wrap"><table className="rx-table"><thead><tr><th>{tr('rx.time')}</th>{SENSORS.map(n => <th key={n}>{tr(`rx.sensor.${n}`)}</th>)}{RELAYS.map(r => <th key={r}>{tr(`rx.relay.${r}`)}</th>)}</tr></thead>
        <tbody>{points.slice(-20).reverse().map(p => <tr key={p.t}><td>{clock(p.t)}</td>{SENSORS.map(n => <td key={n}>{formatValue(n, p[n])}</td>)}{RELAYS.map(r => <td key={r}>{p[`relay_${r}`] ? tr('rx.on') : tr('rx.off')}</td>)}</tr>)}</tbody></table></div>
    </details>
  </section>
}

// ---------------------------------------------------------------- relays
type Pending = { kind: 'relay'; relay: RelayName; on: boolean } | { kind: 'reset' }

function RelayCard({ relay, status, onAsk, big }: { relay: RelayName; status: ReactorStatus; onAsk: (p: Pending) => void; big?: boolean }) {
  const state = status.relays[relay]
  const Icon = RELAY_ICONS[relay]
  const blockedOn = !state.on ? state.on_blocked : null
  const disabled = !status.controls_enabled || Boolean(blockedOn)
  return <article className={`rx-relay ds-card ${state.on ? 'is-on' : ''} ${big ? 'rx-relay-big' : ''}`} data-testid={`rx-relay-${relay}`}>
    <div className="rx-relay-head"><Icon size={big ? 30 : 22} aria-hidden="true" /><strong>{tr(`rx.relay.${relay}`)}</strong>
      <span className={`rx-relay-state ${state.on ? 'is-on' : ''}`} data-testid={`rx-relay-state-${relay}`}>{state.on ? tr('rx.on') : tr('rx.off')}</span></div>
    {!big && <p className="rx-relay-time">{state.on ? tr('rx.runningFor', { time: duration(state.on_for_s) }) : tr('rx.stopped')} · {tr('rx.totalFor', { time: duration(state.total_s) })}</p>}
    {big && state.on && <p className="rx-relay-time">{tr('rx.runningFor', { time: duration(state.on_for_s) })}</p>}
    {!big && <button className={`ds-button ${state.on ? '' : 'ds-button-primary'}`} disabled={disabled} data-testid={`rx-relay-button-${relay}`}
      onClick={() => onAsk({ kind: 'relay', relay, on: !state.on })}>{state.on ? tr('rx.turnOff') : tr('rx.turnOn')}</button>}
    {!big && blockedOn && status.controls_enabled && <p className="rx-relay-blocked" data-testid={`rx-relay-blocked-${relay}`}>{tr(`rx.reason.${blockedOn}`)}</p>}
  </article>
}

function ConfirmDialog({ pending, onCancel, onConfirm, busy }: { pending: Pending; onCancel: () => void; onConfirm: () => void; busy: boolean }) {
  const confirmRef = useRef<HTMLButtonElement>(null)
  useEffect(() => { confirmRef.current?.focus() }, [])
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onCancel() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onCancel])
  const title = pending.kind === 'reset' ? tr('rx.confirm.resetTitle') : tr(pending.on ? 'rx.confirm.onTitle' : 'rx.confirm.offTitle', { relay: tr(`rx.relay.${pending.relay}`) })
  const text = pending.kind === 'reset' ? tr('rx.confirm.resetText') : pending.on ? tr(`rx.confirm.on.${pending.relay}`) : tr('rx.confirm.offText')
  return <div className="rx-modal-backdrop" role="presentation" onClick={onCancel}>
    <div className="rx-modal ds-card" role="dialog" aria-modal="true" aria-labelledby="rx-confirm-title" onClick={event => event.stopPropagation()} data-testid="rx-confirm">
      <h2 id="rx-confirm-title">{title}</h2><p>{text}</p>
      <div className="rx-modal-actions"><button className="ds-button" onClick={onCancel}>{tr('rx.cancel')}</button>
        <button ref={confirmRef} className="ds-button ds-button-primary" onClick={onConfirm} disabled={busy} data-testid="rx-confirm-yes">{tr('rx.confirmYes')}</button></div>
    </div>
  </div>
}

// ---------------------------------------------------------------- alarms
function LeakAlarm({ status, onReset }: { status: ReactorStatus; onReset: () => void }) {
  const leak = status.alarms.find(a => a.code === 'leak')
  const [collapsedFor, setCollapsedFor] = useState<number | null>(null)
  if (!leak) return null
  const collapsed = collapsedFor !== null && collapsedFor === leak.since
  const body = <>
    <p>{tr('rx.leak.text', { value: formatValue('gas_out', status.readings.gas_out.value ?? status.readings.gas_out.last), leak: status.thresholds?.gas_out_raw.leak ?? '—' })}</p>
    <p>{leak.still_leaking ? tr('rx.leak.still') : tr('rx.leak.gone')}</p>
    <div className="rx-alarm-actions">
      <button className="ds-button rx-alarm-reset" disabled={Boolean(leak.still_leaking) || !status.controls_enabled} onClick={onReset} data-testid="rx-leak-reset">{tr('rx.leak.reset')}</button>
      {!collapsed && <button className="ds-button" onClick={() => setCollapsedFor(leak.since ?? 0)}>{tr('rx.leak.collapse')}</button>}
    </div>
  </>
  if (collapsed) return <section className="rx-alarm-strip" role="alert" data-testid="rx-leak-strip"><AlertOctagon size={22} /><strong>{tr('rx.leak.title')}</strong>{body}</section>
  return <div className="rx-alarm-overlay" role="alertdialog" aria-modal="true" aria-labelledby="rx-leak-title" data-testid="rx-leak-alarm">
    <div className="rx-alarm-box"><AlertOctagon size={64} aria-hidden="true" /><h2 id="rx-leak-title">{tr('rx.leak.title')}</h2>
      <p className="rx-alarm-lead">{tr('rx.leak.heaterOff')}</p>{body}</div>
  </div>
}

function OtherAlarms({ status }: { status: ReactorStatus }) {
  const list = status.alarms.filter(a => !['leak', 'pi_lost', 'arduino_lost'].includes(a.code))
  if (!list.length) return null
  return <div className="rx-alarms" data-testid="rx-alarms">{list.map(a =>
    <div key={a.code} className={`rx-alarm-line rx-tone-${a.level}`} role={a.level === 'danger' ? 'alert' : 'status'}>
      {a.level === 'danger' ? <AlertOctagon size={18} /> : <AlertTriangle size={18} />}<span>{tr(`rx.alarm.${a.code}`)}</span></div>)}</div>
}

// ---------------------------------------------------------------- simulator, journal, chain
const SIM_SWITCHES: SimulatorSwitch[] = ['leak', 'usb', 'arduino_silent', 'temp_sensor', 'network']

function SimulatorPanel({ status, onChange }: { status: ReactorStatus; onChange: () => void }) {
  const [busy, setBusy] = useState(false)
  if (!status.simulator) return null
  const flip = async (what: SimulatorSwitch) => {
    setBusy(true)
    try { await reactorApi.simulate(what, !status.simulator?.[what]) } finally { setBusy(false); onChange() }
  }
  return <section className="rx-section ds-card rx-sim" data-testid="rx-simulator">
    <h2><Cpu size={18} /> {tr('rx.sim.title')}</h2><p className="ds-muted">{tr('rx.sim.lead')}</p>
    <div className="rx-sim-buttons">{SIM_SWITCHES.map(what => <button key={what} className={`ds-button ${status.simulator?.[what] ? 'is-active' : ''}`} aria-pressed={Boolean(status.simulator?.[what])}
      disabled={busy || (what !== 'network' && !status.link.network_ok)} onClick={() => flip(what)} data-testid={`rx-sim-${what}`}>
      {tr(`rx.sim.${what}`)}{status.simulator?.[what] ? ` — ${tr('rx.sim.active')}` : ''}</button>)}</div>
  </section>
}

function Journal() {
  const [items, setItems] = useState<JournalItem[]>([])
  const [live, setLive] = useState(true)
  useEffect(() => {
    const controller = new AbortController()
    const load = () => reactorApi.journal(controller.signal).then(r => { if (r.live) setItems(r.items); setLive(r.live) }).catch(() => setLive(false))
    load()
    const timer = setInterval(load, 5000)
    return () => { controller.abort(); clearInterval(timer) }
  }, [])
  const what = (item: JournalItem) => { const key = `rx.j.${item.what}`; const text = tr(key); return text === key ? item.what : text }
  const who = (item: JournalItem) => { const key = `rx.who.${item.who}`; const text = tr(key); return text === key ? item.who : text }
  return <section className="rx-section ds-card" data-testid="rx-journal">
    <h2>{tr('rx.journal')}</h2><p className="ds-muted">{tr('rx.journalLead')}</p>
    {!live && <p className="ds-muted">{tr('rx.journalStale')}</p>}
    <div className="rx-table-wrap"><table className="rx-table"><thead><tr><th>{tr('rx.time')}</th><th>{tr('rx.j.what')}</th><th>{tr('rx.j.who')}</th><th>{tr('rx.j.result')}</th></tr></thead>
      <tbody>{items.map(item => <tr key={item.id} className={`rx-j-${item.kind}`}><td>{new Date(item.ts).toLocaleTimeString()}</td><td>{what(item)}</td><td>{who(item)}</td><td className="rx-mono">{item.result ?? ''}</td></tr>)}</tbody></table></div>
  </section>
}

const CHAIN = () => [
  { icon: Thermometer, title: tr('rx.chain.sensors'), text: tr('rx.chain.sensorsText') },
  { icon: Cpu, title: 'Arduino', text: tr('rx.chain.arduinoText') },
  { icon: Cable, title: 'USB', text: tr('rx.chain.usbText') },
  { icon: RadioTower, title: 'Raspberry Pi', text: tr('rx.chain.piText') },
  { icon: Network, title: tr('rx.chain.network'), text: tr('rx.chain.networkText') },
  { icon: Laptop, title: tr('rx.chain.laptop'), text: tr('rx.chain.laptopText') },
  { icon: Bot, title: tr('rx.chain.agent'), text: tr('rx.chain.agentText') },
]

function Chain() {
  return <details className="ds-collapse rx-chain-block" data-testid="rx-chain"><summary><Wrench size={15} /> {tr('rx.chain.title')}</summary>
    <ol className="reactor-chain-list">{CHAIN().map((step, index, all) => <li key={step.title}>
      <div className="reactor-chain-step"><step.icon size={22} /><strong>{step.title}</strong><span>{step.text}</span></div>
      {index < all.length - 1 && <ArrowRight className="reactor-chain-arrow" size={18} aria-hidden="true" />}</li>)}</ol>
    <p className="ds-muted">{tr('rx.chain.safety')}</p>
  </details>
}

// ---------------------------------------------------------------- page
export default function Reactor() {
  const [status, setStatus] = useState<ReactorStatus | null>(null)
  const [serverDown, setServerDown] = useState(false)
  const [pending, setPending] = useState<Pending | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)
  const [jury, setJury] = useState(() => readStorage(JURY_KEY) === '1')
  const failures = useRef(0)

  const refresh = useCallback(async (signal?: AbortSignal) => {
    try {
      const next = await reactorApi.status(signal)
      failures.current = 0
      setStatus(next); setServerDown(false)
    } catch {
      if (signal?.aborted) return
      failures.current += 1
      if (failures.current >= 3) setServerDown(true)
    }
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    refresh(controller.signal)
    const timer = setInterval(() => refresh(controller.signal), 1000)
    return () => { controller.abort(); clearInterval(timer) }
  }, [refresh])
  useEffect(() => { writeStorage(JURY_KEY, jury ? '1' : '0') }, [jury])

  const confirm = async () => {
    if (!pending) return
    setBusy(true)
    try {
      const result = pending.kind === 'reset' ? await reactorApi.resetLeak() : await reactorApi.relay(pending.relay, pending.on)
      const done = pending.kind === 'reset' ? tr('rx.done.reset') : tr(pending.on ? 'rx.done.on' : 'rx.done.off', { relay: tr(`rx.relay.${pending.relay}`) })
      setMessage(result.ok ? { ok: true, text: done } : { ok: false, text: tr('rx.refused', { reason: tr(`rx.reason.${result.reason ?? 'unknown'}`) }) })
    } catch (error) {
      setMessage({ ok: false, text: String((error as Error).message ?? error) })
    } finally { setBusy(false); setPending(null); refresh() }
  }

  const controls = Boolean(status?.controls_enabled) && !serverDown
  const shown = status && serverDown ? { ...status, controls_enabled: false, link: { ...status.link, ok: false } } : status
  return <div className={`reactor-page rx-page ${jury ? 'rx-jury' : ''}`} data-testid="reactor-page">
    <div className="page-heading rx-heading"><div><h1>{tr('rx.title')}</h1><p>{tr('rx.lead')}</p></div>
      <div className="rx-heading-actions"><SourceBadge status={status} /><CheckButton />
        <button className={`ds-button ${jury ? 'ds-button-primary' : ''}`} aria-pressed={jury} onClick={() => setJury(!jury)} data-testid="rx-jury"><Gavel size={16} />{tr('rx.jury')}</button></div></div>

    <LinkBanner status={status} serverDown={serverDown} />
    {shown && <LeakAlarm status={shown} onReset={() => setPending({ kind: 'reset' })} />}
    {shown && <OtherAlarms status={shown} />}
    {message && <div className={`rx-message ${message.ok ? 'is-ok' : 'is-bad'}`} role="status" data-testid="rx-message">
      {message.ok ? <CheckCircle2 size={18} /> : <XCircle size={18} />}<span>{message.text}</span>
      <button className="rx-message-close" onClick={() => setMessage(null)} aria-label={tr('rx.close')}>×</button></div>}

    {!shown ? <div className="rx-loading ds-card" role="status">{tr('rx.loading')}</div> : jury ?
      <section className="rx-jury-panel" data-testid="rx-jury-panel" aria-label={tr('rx.jury')}>
        <SourceBadge status={shown} big />
        <div className="rx-jury-readings">{SENSORS.map(name => <ReadingCard key={name} name={name} status={shown} big />)}</div>
        <div className="rx-jury-relays">{RELAYS.map(relay => <RelayCard key={relay} relay={relay} status={shown} onAsk={setPending} big />)}</div>
        <p className="rx-agent-note"><Bot size={18} /> {tr('rx.agentNote')}</p>
      </section> :
      <>
        <div className="rx-readings">{SENSORS.map(name => <ReadingCard key={name} name={name} status={shown} />)}</div>
        <section className="rx-section" aria-labelledby="rx-relays-title">
          <div className="rx-section-head"><h2 id="rx-relays-title">{tr('rx.relays')}</h2></div>
          <p className="ds-muted">{controls ? tr('rx.relaysLead') : tr('rx.relaysLocked')}</p>
          <div className="rx-relays">{RELAYS.map(relay => <RelayCard key={relay} relay={relay} status={shown} onAsk={setPending} />)}</div>
          <p className="rx-agent-note"><Bot size={18} /> {tr('rx.agentNote')}</p>
        </section>
      </>}
    {shown && <Charts status={shown} />}
    {shown && !jury && <SimulatorPanel status={shown} onChange={() => refresh()} />}
    {!jury && <Journal />}
    <Chain />
    {pending && <ConfirmDialog pending={pending} busy={busy} onCancel={() => setPending(null)} onConfirm={confirm} />}
  </div>
}

