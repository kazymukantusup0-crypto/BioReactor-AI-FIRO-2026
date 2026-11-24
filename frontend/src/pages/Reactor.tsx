// «Реактор»: live sensors, the Arduino's automatic mode, manual relays, thresholds, E-STOP.
// Chain: Arduino (firmware bioreactor-1.0, main protection + AUTO) -> USB -> Raspberry Pi -> network -> this page.
// The page only shows what the Pi reports. Every manual command is a person's button + a confirmation; E-STOP is one
// click with no confirmation. The AI agent reads the same data and never presses buttons.
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { AlertOctagon, AlertTriangle, ArrowRight, Bot, Cable, CheckCircle2, Cog, Cpu, Droplets, Fan, Flame, Gavel, HelpCircle, Laptop, Network, OctagonX, PlugZap, Power, RadioTower, RefreshCw, RotateCcw, ShieldAlert, SlidersHorizontal, Snowflake, Thermometer, Unplug, Wifi, Wind, Wrench, XCircle } from 'lucide-react'
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ALARM_CODES, LIMITS, reactorApi, RELAYS, SENSORS, type Alarm, type CheckResult, type CommandResult, type HistoryPoint, type JournalItem, type Level, type LimitName, type Limits, type ReactorStatus, type RelayName, type SensorName, type SimulatorSwitch } from '../reactorApi'
import { tr } from '../i18n'
import '../reactor.css'
import { chartColors } from '../theme'

const JURY_KEY = 'bioreactor-reactor-jury'
const ICONS: Record<SensorName, typeof Thermometer> = { temp_c: Thermometer, rh_pct: Droplets, gas_in: Wind, gas_out: ShieldAlert }
// relay 1 heat, 2 cool, 3 mixer (API name pump), 4 compressor (API name auger)
const RELAY_ICONS: Record<RelayName, typeof Flame> = { heat: Flame, cool: Snowflake, pump: RefreshCw, auger: Wind }
const DIGITS: Record<SensorName, number> = { temp_c: 1, rh_pct: 1, gas_in: 0, gas_out: 0 }
// Same ranges as validSettings() in the sketch; the step is the encoder's step on the Arduino screen
const LIMIT_INPUT: Record<LimitName, { min: number; max: number; step: number }> = {
  temp_min: { min: 0, max: 67.5, step: 0.5 }, temp_max: { min: 0.5, max: 68, step: 0.5 }, temp_hard_max: { min: 2.5, max: 70, step: 0.5 },
  gas_out_limit: { min: 50, max: 1000, step: 10 }, gas_in_limit: { min: 50, max: 1000, step: 10 },
}
const isTempLimit = (name: LimitName) => name.startsWith('temp')

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
const limitText = (name: LimitName, value: number) => isTempLimit(name) ? `${value.toFixed(1)} °C` : String(Math.round(value))
const reasonText = (reason: string | null | undefined) => { const key = `rx.reason.${reason ?? 'unknown'}`; const text = tr(key); return text === key ? (reason ?? '') : text }

function LevelChip({ level }: { level: Level }) {
  const Icon = level === 'ok' ? CheckCircle2 : level === 'warn' ? AlertTriangle : level === 'danger' ? AlertOctagon : HelpCircle
  return <span className={`rx-level rx-level-${level}`}><Icon size={15} aria-hidden="true" />{levelText(level)}</span>
}

// ---------------------------------------------------------------- source and link
export function SourceBadge({ status, big = false }: { status: ReactorStatus | null; big?: boolean }) {
  if (!status) return <span className={`rx-source rx-source-unknown ${big ? 'rx-big' : ''}`} data-testid="rx-source"><Cable size={16} />{tr('rx.source.unknown')}</span>
  const simulator = status.source.kind === 'simulator'
  const route = status.source.route
  return <span className={`rx-source ${simulator ? 'rx-source-sim' : 'rx-source-pi'} ${big ? 'rx-big' : ''}`} data-testid="rx-source">
    {simulator ? <Cpu size={16} /> : <RadioTower size={16} />}
    {simulator ? tr('rx.source.sim')
      // a real Pi started with --simulate: the network is real, the sensors are not — say so
      : status.source.arduino_port === 'virtual' ? tr('rx.source.piVirtual', { address: status.source.address ?? '?' })
      : tr('rx.source.pi', { address: status.source.address ?? '?' })}
    {!simulator && route && <span className="rx-route" data-testid="rx-route">{route === 'pi_wifi' ? <Wifi size={14} /> : route === 'cable' ? <Cable size={14} /> : <Network size={14} />}{tr(`rx.route.${route}`)}</span>}
  </span>
}

function LinkBanner({ status, serverDown }: { status: ReactorStatus | null; serverDown: boolean }) {
  if (!serverDown && status?.link.ok) return null
  const starting = !serverDown && status?.alarms.some(a => a.code === 'arduino_starting')
  const level = serverDown ? 'server' : starting ? 'starting' : status?.link.level === 'arduino' ? 'arduino' : 'pi'
  return <section className={`rx-nolink ${starting ? 'is-starting' : ''}`} role="alert" data-testid="rx-nolink">
    <PlugZap size={34} aria-hidden="true" />
    <div><h2>{tr(`rx.nolink.${level}`)}</h2><p>{tr(`rx.nolink.${level}Text`)}</p>
      {status?.link.error && !serverDown && !starting && <p className="rx-mono">{status.link.error}</p>}</div>
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
      {result.ok ? tr('rx.checkOk', { ms: result.latency_ms, port: result.port ?? '—', arduino: result.arduino_ok ? tr('rx.yes') : tr('rx.no'), route: result.route ? tr(`rx.route.${result.route}`) : result.url })
        : tr('rx.checkFail', { error: result.error ?? '' })}
    </span>}
  </div>
}

// ---------------------------------------------------------------- E-STOP and reset (always on top)
function EmergencyBar({ status, onEstop, onReset, busy }: { status: ReactorStatus; onEstop: () => void; onReset: () => void; busy: boolean }) {
  const needsReset = status.alarms.some(a => a.needs_reset)
  return <section className="rx-estop-bar" aria-label={tr('rx.estop.label')} data-testid="rx-estop-bar">
    <button className="rx-estop" onClick={onEstop} disabled={!status.estop_enabled || busy} data-testid="rx-estop">
      {status.estop_enabled ? <OctagonX size={26} aria-hidden="true" /> : <Unplug size={26} aria-hidden="true" />}
      <span><strong>{tr('rx.estop.button')}</strong><small>{status.estop_enabled ? tr('rx.estop.hint') : tr('rx.estop.noLink')}</small></span></button>
    <button className="ds-button rx-reset-button" onClick={onReset} disabled={!needsReset || !status.controls_enabled || busy} data-testid="rx-reset">
      <RotateCcw size={16} />{tr('rx.reset.button')}</button>
    <p className="ds-muted">{needsReset ? tr('rx.reset.needed') : tr('rx.reset.none')}</p>
  </section>
}

// ---------------------------------------------------------------- alarms
const BIG_ALARMS = ['estop', 'leak']

function alarmBody(alarm: Alarm, status: ReactorStatus): string {
  if (alarm.code === 'leak') return tr('rx.alarm.leakText', { value: formatValue('gas_out', status.readings.gas_out.value ?? status.readings.gas_out.last), limit: status.limits?.gas_out_limit ?? '—' })
  if (alarm.code === 'overheat') return tr('rx.alarm.overheat', { limit: status.limits?.temp_hard_max ?? '—' })
  return tr(`rx.alarm.${alarm.code}`)
}

function BigAlarm({ status, onReset }: { status: ReactorStatus; onReset: () => void }) {
  const alarm = status.alarms.find(a => BIG_ALARMS.includes(a.code))
  const [collapsedFor, setCollapsedFor] = useState<string | null>(null)
  if (!alarm) return null
  const id = `${alarm.code}:${alarm.since ?? ''}`
  const collapsed = collapsedFor === id
  const blocked = alarm.code === 'leak' && alarm.still_leaking
  const body = <>
    <p>{alarmBody(alarm, status)}</p>
    {alarm.code === 'leak' && <p>{blocked ? tr('rx.leak.still') : tr('rx.leak.gone')}</p>}
    <div className="rx-alarm-actions">
      <button className="ds-button rx-alarm-reset" disabled={Boolean(blocked) || !status.controls_enabled} onClick={onReset} data-testid="rx-alarm-reset">{tr('rx.reset.button')}</button>
      {!collapsed && <button className="ds-button" onClick={() => setCollapsedFor(id)}>{tr('rx.alarm.collapse')}</button>}
    </div>
  </>
  if (collapsed) return <section className="rx-alarm-strip" role="alert" data-testid={`rx-${alarm.code}-strip`}><AlertOctagon size={22} /><strong>{tr(`rx.alarm.${alarm.code}Title`)}</strong>{body}</section>
  return <div className="rx-alarm-overlay" role="alertdialog" aria-modal="true" aria-labelledby="rx-alarm-title" data-testid={`rx-${alarm.code}-alarm`}>
    <div className="rx-alarm-box"><AlertOctagon size={64} aria-hidden="true" /><h2 id="rx-alarm-title">{tr(`rx.alarm.${alarm.code}Title`)}</h2>
      <p className="rx-alarm-lead">{tr(`rx.alarm.${alarm.code}Lead`)}</p>{body}</div>
  </div>
}

function AlarmList({ status }: { status: ReactorStatus }) {
  const order = ALARM_CODES as readonly string[]
  const list = status.alarms.filter(a => order.includes(a.code)).sort((a, b) => order.indexOf(a.code) - order.indexOf(b.code))
  if (!list.length) return null
  return <div className="rx-alarms" data-testid="rx-alarms">{list.map(a =>
    <div key={a.code} className={`rx-alarm-line rx-tone-${a.level}`} role={a.level === 'danger' ? 'alert' : 'status'} data-testid={`rx-alarm-${a.code}`}>
      {a.level === 'danger' ? <AlertOctagon size={20} /> : <AlertTriangle size={20} />}
      <strong>{tr(`rx.alarm.${a.code}Title`)}</strong><span>{alarmBody(a, status)}</span></div>)}</div>
}

// ---------------------------------------------------------------- readings
function readingNote(name: SensorName, status: ReactorStatus): string {
  const l = status.limits
  if (name === 'rh_pct') return tr('rx.note.rh')
  if (!l) return ''
  if (name === 'temp_c') return tr('rx.note.temp', { low: l.temp_min, high: l.temp_max, over: l.temp_hard_max })
  if (name === 'gas_in') return tr('rx.note.gasIn', { limit: l.gas_in_limit })
  return tr('rx.note.gasOut', { limit: l.gas_out_limit })
}

function ReadingCard({ name, status, big }: { name: SensorName; status: ReactorStatus; big?: boolean }) {
  const reading = status.readings[name]
  const Icon = ICONS[name]
  const stale = !status.link.ok
  return <article className={`rx-reading ds-card rx-tone-${reading.level} ${big ? 'rx-reading-big' : ''}`} data-testid={`rx-reading-${name}`}>
    <span className="rx-reading-title"><Icon size={18} aria-hidden="true" />{tr(`rx.sensor.${name}`)}</span>
    <strong className="rx-reading-value">{formatValue(name, reading.value)}<small>{unit(name)}</small></strong>
    <LevelChip level={reading.level} />
    {!big && <span className="rx-reading-note">{readingNote(name, status)}</span>}
    {stale && reading.last !== null && <span className="rx-reading-stale">{tr('rx.lastKnown', { value: formatValue(name, reading.last), unit: unit(name) })}</span>}
  </article>
}

// ---------------------------------------------------------------- charts (one small chart per measure: never two scales)
function thresholdLines(name: SensorName, l: Limits | null): { y: number; tone: 'warn' | 'danger' | 'target'; label: string }[] {
  if (!l) return []
  if (name === 'temp_c') return [{ y: l.temp_min, tone: 'target', label: tr('rx.line.min') }, { y: l.temp_max, tone: 'warn', label: tr('rx.line.max') }, { y: l.temp_hard_max, tone: 'danger', label: tr('rx.line.overheat') }]
  if (name === 'gas_in') return [{ y: l.gas_in_limit, tone: 'warn', label: tr('rx.line.pump') }]
  if (name === 'gas_out') return [{ y: l.gas_out_limit, tone: 'danger', label: tr('rx.line.leak') }]
  return [{ y: 95, tone: 'warn', label: '' }]
}
const clock = (t: number) => new Date(t * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })

function SensorChart({ name, points, limits }: { name: SensorName; points: HistoryPoint[]; limits: Limits | null }) {
  const data = points.map(p => ({ t: p.t, v: p[name] }))
  const c = chartColors()
  const lineColor = { warn: c.warn, danger: c.danger, target: c.info }
  return <figure className="rx-chart ds-card" data-testid={`rx-chart-${name}`}>
    <figcaption>{tr(`rx.sensor.${name}`)}<span>, {unit(name)}</span></figcaption>
    {data.length < 2 ? <p className="ds-muted rx-chart-empty">{tr('rx.chartEmpty')}</p> :
      <div className="rx-chart-box"><ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 10, right: 12, bottom: 0, left: -12 }}>
          <CartesianGrid stroke={c.grid} strokeDasharray="3 5" vertical={false} />
          <XAxis dataKey="t" type="number" domain={['dataMin', 'dataMax']} tickFormatter={v => clock(Number(v)).slice(0, 5)} axisLine={false} tickLine={false} tick={{ fill: c.tick, fontSize: 13, fontFamily: c.fontFamily }} minTickGap={40} />
          <YAxis domain={['auto', 'auto']} axisLine={false} tickLine={false} tick={{ fill: c.tick, fontSize: 13, fontFamily: c.fontFamily }} width={52} tickFormatter={v => Number(v).toFixed(0)} />
          {thresholdLines(name, limits).map(line => <ReferenceLine key={`${line.tone}${line.y}`} y={line.y} stroke={lineColor[line.tone]} strokeDasharray={line.tone === 'target' ? '2 4' : '6 4'} ifOverflow="extendDomain"
            label={line.label ? { value: line.label, position: 'insideTopRight', fill: c.label, fontSize: 13 } : undefined} />)}
          <Tooltip contentStyle={{ background: c.tooltipBg, border: `1px solid ${c.tooltipBorder}`, borderRadius: 10, color: c.tooltipText }} labelFormatter={v => clock(Number(v))}
            formatter={value => [`${formatValue(name, value as number | null)} ${unit(name)}`, tr(`rx.sensor.${name}`)]} />
          <Line type="monotone" dataKey="v" stroke={c.line} strokeWidth={2} dot={false} activeDot={{ r: 5, stroke: c.surface, strokeWidth: 2 }} isAnimationActive={false} connectNulls={false} />
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
    <div className="rx-charts">{SENSORS.map(name => <SensorChart key={name} name={name} points={points} limits={status.limits} />)}</div>
    <details className="ds-collapse rx-table-view"><summary>{tr('rx.tableView')}</summary>
      <div className="rx-table-wrap"><table className="rx-table"><thead><tr><th>{tr('rx.time')}</th>{SENSORS.map(n => <th key={n}>{tr(`rx.sensor.${n}`)}</th>)}{RELAYS.map(r => <th key={r}>{tr(`rx.relay.${r}`)}</th>)}</tr></thead>
        <tbody>{points.slice(-20).reverse().map(p => <tr key={p.t}><td>{clock(p.t)}</td>{SENSORS.map(n => <td key={n}>{formatValue(n, p[n])}</td>)}{RELAYS.map(r => <td key={r}>{p[`relay_${r}`] ? tr('rx.on') : tr('rx.off')}</td>)}</tr>)}</tbody></table></div>
    </details>
  </section>
}

// ---------------------------------------------------------------- confirmation
type Pending = { kind: 'relay'; relay: RelayName; on: boolean } | { kind: 'reset' } | { kind: 'auto'; on: boolean }
  | { kind: 'limit'; name: LimitName; value: number; was: number }

function ConfirmDialog({ pending, onCancel, onConfirm, busy }: { pending: Pending; onCancel: () => void; onConfirm: () => void; busy: boolean }) {
  const confirmRef = useRef<HTMLButtonElement>(null)
  useEffect(() => { confirmRef.current?.focus() }, [])
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onCancel() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onCancel])
  let title: string, text: string
  if (pending.kind === 'reset') { title = tr('rx.confirm.resetTitle'); text = tr('rx.confirm.resetText') }
  else if (pending.kind === 'auto') { title = tr(pending.on ? 'rx.confirm.autoOnTitle' : 'rx.confirm.autoOffTitle'); text = tr(pending.on ? 'rx.confirm.autoOnText' : 'rx.confirm.autoOffText') }
  else if (pending.kind === 'limit') { title = tr('rx.confirm.limitTitle', { limit: tr(`rx.limit.${pending.name}`) }); text = tr('rx.confirm.limitText', { was: limitText(pending.name, pending.was), value: limitText(pending.name, pending.value) }) }
  else { title = tr(pending.on ? 'rx.confirm.onTitle' : 'rx.confirm.offTitle', { relay: tr(`rx.relay.${pending.relay}`) }); text = pending.on ? tr(`rx.confirm.on.${pending.relay}`) : tr('rx.confirm.offText') }
  return <div className="rx-modal-backdrop" role="presentation" onClick={onCancel}>
    <div className="rx-modal ds-card" role="dialog" aria-modal="true" aria-labelledby="rx-confirm-title" onClick={event => event.stopPropagation()} data-testid="rx-confirm">
      <h2 id="rx-confirm-title">{title}</h2><p>{text}</p>
      <div className="rx-modal-actions"><button className="ds-button" onClick={onCancel}>{tr('rx.cancel')}</button>
        <button ref={confirmRef} className="ds-button ds-button-primary" onClick={onConfirm} disabled={busy} data-testid="rx-confirm-yes">{tr('rx.confirmYes')}</button></div>
    </div>
  </div>
}

// ---------------------------------------------------------------- mode, relays, limits
function ModeCard({ status, onAsk }: { status: ReactorStatus; onAsk: (p: Pending) => void }) {
  const auto = Boolean(status.auto)
  const locked = Boolean(status.arduino_alarms?.estop || status.arduino_alarms?.leak)
  return <article className={`rx-mode ds-card ${auto ? 'is-auto' : ''}`} data-testid="rx-mode">
    <div className="rx-relay-head"><SlidersHorizontal size={22} aria-hidden="true" /><strong>{tr('rx.mode.title')}</strong>
      <span className={`rx-relay-state ${auto ? 'is-on' : ''}`} data-testid="rx-mode-state">{status.auto === null ? '—' : auto ? tr('rx.mode.auto') : tr('rx.mode.manual')}</span></div>
    <p className="rx-relay-time">{auto ? tr('rx.mode.autoText') : tr('rx.mode.manualText')}</p>
    <ControlButton status={status} primary={!auto} disabled={!status.controls_enabled || (!auto && locked)} testId="rx-mode-button"
      onClick={() => onAsk({ kind: 'auto', on: !auto })}>{auto ? tr('rx.mode.turnOff') : tr('rx.mode.turnOn')}</ControlButton>
    {!auto && locked && status.controls_enabled && <p className="rx-relay-blocked">{tr(`rx.reason.${status.arduino_alarms?.estop ? 'estop' : 'leak'}`)}</p>}
  </article>
}

// A control button that says plainly when it cannot work: no link -> grey, plug icon, «Нет связи» instead of the action.
// A disabled button is never filled with the accent colour (on a projector a filled button reads as clickable).
function ControlButton({ status, primary, disabled, testId, onClick, children }: { status: ReactorStatus; primary?: boolean; disabled: boolean; testId: string; onClick: () => void; children: ReactNode }) {
  const offline = !status.link.ok
  return <button className={`ds-button ${primary && !disabled ? 'ds-button-primary' : ''} ${offline ? 'rx-offline-button' : ''}`} disabled={disabled} data-testid={testId}
    title={offline ? tr('rx.noLinkButton.hint') : undefined} onClick={onClick}>
    {offline ? <><Unplug size={16} aria-hidden="true" />{tr('rx.noLinkButton')}</> : children}</button>
}

function RelayCard({ relay, status, onAsk, big }: { relay: RelayName; status: ReactorStatus; onAsk: (p: Pending) => void; big?: boolean }) {
  const state = status.relays[relay]
  const Icon = RELAY_ICONS[relay]
  const blockedOn = !state.on ? state.on_blocked : null
  const disabled = !status.controls_enabled || Boolean(blockedOn)
  const offline = !status.link.ok
  const who = state.on ? (state.remote ? tr('rx.who.fromLaptop') : tr('rx.who.byArduino')) : null
  return <article className={`rx-relay ds-card ${state.on ? 'is-on' : ''} ${offline ? 'is-offline' : ''} ${big ? 'rx-relay-big' : ''}`} data-testid={`rx-relay-${relay}`}>
    <div className="rx-relay-head"><Icon size={big ? 30 : 22} aria-hidden="true" /><strong>{tr(`rx.relay.${relay}`)}</strong>
      <span className={`rx-relay-state ${state.on ? 'is-on' : ''} ${offline ? 'is-offline' : ''}`} data-testid={`rx-relay-state-${relay}`}>{offline ? tr('rx.state.noLink') : state.on ? tr('rx.on') : tr('rx.off')}</span></div>
    {who && <p className="rx-relay-who" data-testid={`rx-relay-who-${relay}`}>{who}</p>}
    {!big && <p className="rx-relay-time">{state.on ? tr('rx.runningFor', { time: duration(state.on_for_s) }) : tr('rx.stopped')} · {tr('rx.totalFor', { time: duration(state.total_s) })}</p>}
    {big && state.on && <p className="rx-relay-time">{tr('rx.runningFor', { time: duration(state.on_for_s) })}</p>}
    {!big && <ControlButton status={status} primary={!state.on} disabled={disabled} testId={`rx-relay-button-${relay}`}
      onClick={() => onAsk({ kind: 'relay', relay, on: !state.on })}>{state.on ? tr('rx.turnOff') : tr('rx.turnOn')}</ControlButton>}
    {!big && blockedOn && status.controls_enabled && <p className="rx-relay-blocked" data-testid={`rx-relay-blocked-${relay}`}>{reasonText(blockedOn)}</p>}
    {!big && relay === 'auger' && <p className="rx-reading-note">{tr('rx.relay.augerNote')}</p>}
  </article>
}

function LimitRow({ name, status, onAsk }: { name: LimitName; status: ReactorStatus; onAsk: (p: Pending) => void }) {
  const current = status.limits?.[name]
  const [draft, setDraft] = useState<string>('')
  useEffect(() => { if (current !== undefined) setDraft(String(current)) }, [current])
  const input = LIMIT_INPUT[name]
  const value = Number(draft)
  const valid = draft.trim() !== '' && Number.isFinite(value) && value >= input.min && value <= input.max
  const changed = current !== undefined && valid && value !== current
  return <div className="rx-limit" data-testid={`rx-limit-${name}`}>
    <label htmlFor={`rx-limit-input-${name}`}><strong>{tr(`rx.limit.${name}`)}</strong><span>{tr(`rx.limit.${name}Hint`)}</span></label>
    <span className="rx-limit-now">{current === undefined ? '—' : limitText(name, current)}</span>
    <div className="rx-limit-edit">
      <input id={`rx-limit-input-${name}`} type="number" inputMode="decimal" min={input.min} max={input.max} step={input.step} value={draft}
        onChange={event => setDraft(event.target.value)} disabled={!status.controls_enabled} aria-invalid={!valid} data-testid={`rx-limit-input-${name}`} />
      <span className="rx-limit-unit">{isTempLimit(name) ? '°C' : tr('rx.limit.raw')}</span>
      <button className="ds-button" disabled={!status.controls_enabled || !changed} data-testid={`rx-limit-save-${name}`}
        onClick={() => current !== undefined && onAsk({ kind: 'limit', name, value, was: current })}>{tr('rx.limit.save')}</button>
    </div>
  </div>
}

function LimitsPanel({ status, onAsk }: { status: ReactorStatus; onAsk: (p: Pending) => void }) {
  return <section className="rx-section ds-card rx-limits" aria-labelledby="rx-limits-title" data-testid="rx-limits">
    <h2 id="rx-limits-title"><SlidersHorizontal size={18} /> {tr('rx.limits.title')}</h2>
    <p className="ds-muted">{tr('rx.limits.lead')}</p>
    {status.limits ? LIMITS.map(name => <LimitRow key={name} name={name} status={status} onAsk={onAsk} />) : <p className="ds-muted">{tr('rx.limits.unknown')}</p>}
  </section>
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
  { icon: Cpu, title: 'Arduino Mega', text: tr('rx.chain.arduinoText') },
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

  const report = (result: CommandResult, done: string) =>
    setMessage(result.ok ? { ok: true, text: done } : { ok: false, text: tr('rx.refused', { reason: reasonText(result.reason) }) })

  const estop = async () => {
    setBusy(true)
    try { report(await reactorApi.estop(), tr('rx.done.estop')) }
    catch (error) { setMessage({ ok: false, text: String((error as Error).message ?? error) }) }
    finally { setBusy(false); refresh() }
  }

  const confirm = async () => {
    if (!pending) return
    setBusy(true)
    try {
      if (pending.kind === 'reset') report(await reactorApi.resetAlarms(), tr('rx.done.reset'))
      else if (pending.kind === 'auto') report(await reactorApi.auto(pending.on), tr(pending.on ? 'rx.done.autoOn' : 'rx.done.autoOff'))
      else if (pending.kind === 'limit') report(await reactorApi.limit(pending.name, pending.value), tr('rx.done.limit', { limit: tr(`rx.limit.${pending.name}`), value: limitText(pending.name, pending.value) }))
      else report(await reactorApi.relay(pending.relay, pending.on), tr(pending.on ? 'rx.done.on' : 'rx.done.off', { relay: tr(`rx.relay.${pending.relay}`) }))
    } catch (error) {
      setMessage({ ok: false, text: String((error as Error).message ?? error) })
    } finally { setBusy(false); setPending(null); refresh() }
  }

  const controls = Boolean(status?.controls_enabled) && !serverDown
  const shown = status && serverDown ? { ...status, controls_enabled: false, estop_enabled: false, link: { ...status.link, ok: false } } : status
  return <div className={`reactor-page rx-page ${jury ? 'rx-jury' : ''}`} data-testid="reactor-page">
    <div className="page-heading rx-heading"><div><h1>{tr('rx.title')}</h1><p>{tr('rx.lead')}</p></div>
      <div className="rx-heading-actions"><SourceBadge status={status} /><CheckButton />
        <button className={`ds-button ${jury ? 'ds-button-primary' : ''}`} aria-pressed={jury} onClick={() => setJury(!jury)} data-testid="rx-jury"><Gavel size={16} />{tr('rx.jury')}</button></div></div>

    <LinkBanner status={status} serverDown={serverDown} />
    {shown && <EmergencyBar status={shown} onEstop={estop} onReset={() => setPending({ kind: 'reset' })} busy={busy} />}
    {shown && <BigAlarm status={shown} onReset={() => setPending({ kind: 'reset' })} />}
    {shown && <AlarmList status={shown} />}
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
          <div className="rx-relays"><ModeCard status={shown} onAsk={setPending} />{RELAYS.map(relay => <RelayCard key={relay} relay={relay} status={shown} onAsk={setPending} />)}</div>
          <p className="rx-agent-note"><Bot size={18} /> {tr('rx.agentNote')}</p>
        </section>
        <LimitsPanel status={shown} onAsk={setPending} />
      </>}
    {shown && <Charts status={shown} />}
    {shown && !jury && <SimulatorPanel status={shown} onChange={() => refresh()} />}
    {!jury && <Journal />}
    <Chain />
    {pending && <ConfirmDialog pending={pending} busy={busy} onCancel={() => setPending(null)} onConfirm={confirm} />}
  </div>
}
