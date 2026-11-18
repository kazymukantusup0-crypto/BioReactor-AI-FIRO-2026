// «Реактор» page API: Arduino (firmware bioreactor-1.0) -> USB -> Raspberry Pi -> network -> laptop server (/api/reactor/*).
import { request } from './api'

export type Level = 'ok' | 'warn' | 'danger' | 'unknown'
export type RelayName = 'heat' | 'cool' | 'pump' | 'auger'
export type SensorName = 'temp_c' | 'rh_pct' | 'gas_in' | 'gas_out'
export type LimitName = 'temp_min' | 'temp_max' | 'temp_hard_max' | 'gas_out_limit' | 'gas_in_limit'
export type Route = 'pi_wifi' | 'cable' | 'lan'
export const RELAYS: RelayName[] = ['heat', 'cool', 'pump', 'auger']
export const SENSORS: SensorName[] = ['temp_c', 'rh_pct', 'gas_in', 'gas_out']
export const LIMITS: LimitName[] = ['temp_min', 'temp_max', 'temp_hard_max', 'gas_out_limit', 'gas_in_limit']
// Alarms of the Arduino (status.alarms) and of the Pi / laptop, in the order they are shown
export const ALARM_CODES = ['estop', 'leak', 'overheat', 'no_temp', 'link_lost', 'laptop_lost', 'auger_timeout', 'warmup'] as const

export interface Reading { value: number | null; last: number | null; level: Level }
export interface RelayState { on: boolean; remote: boolean; on_for_s: number; total_s: number; on_blocked: string | null }
export interface Alarm { code: string; level: Level; needs_reset?: boolean; still_leaking?: boolean; since?: number | null; error?: string | null }
export type Limits = Record<LimitName, number>
export interface ReactorStatus {
  source: { kind: 'simulator' | 'pi'; mode?: string; address: string | null; route?: Route | null; arduino_port: string | null; firmware: string | null }
  link: { ok: boolean; level: 'pi' | 'arduino' | null; network_ok: boolean; arduino_ok: boolean; seconds_since_pi: number | null; error: string | null }
  readings: Record<SensorName, Reading>
  relays: Record<RelayName, RelayState>
  alarms: Alarm[]
  auto: boolean | null
  limits: Limits | null
  arduino_alarms: Record<string, boolean> | null
  controls_enabled: boolean
  estop_enabled: boolean
  laptop_watchdog: { timeout_s: number; seconds_since_laptop: number; ok: boolean } | null
  simulator: Record<string, boolean> | null
  time: number
}
export interface HistoryPoint { t: number; temp_c: number | null; rh_pct: number | null; gas_in: number | null; gas_out: number | null; relay_heat: number; relay_cool: number; relay_pump: number; relay_auger: number }
export interface JournalItem { id: number; ts: string; kind: string; what: string; who: string; result: string | null; source: string; details: Record<string, unknown> }
export interface CommandResult { ok: boolean; reason: string | null; relays?: Record<RelayName, boolean>; auto?: boolean; limits?: Limits | null; error?: string }
export interface CheckResult { ok: boolean; url: string; mode: string; route?: Route | null; latency_ms: number; arduino_ok?: boolean; port?: string | null; firmware?: string | null; simulated?: boolean; error?: string }
export type SimulatorSwitch = 'leak' | 'usb' | 'arduino_silent' | 'temp_sensor' | 'network'

const root = '/api/reactor'
export const reactorApi = {
  status: (signal?: AbortSignal) => request<ReactorStatus>(`${root}/status`, { signal, timeout: 5000 }),
  history: (window: 600 | 3600, signal?: AbortSignal) => request<{ window: number; points: HistoryPoint[]; live: boolean }>(`${root}/history?window=${window}`, { signal, timeout: 8000 }),
  journal: (signal?: AbortSignal) => request<{ items: JournalItem[]; live: boolean }>(`${root}/journal?limit=40`, { signal, timeout: 8000 }),
  check: () => request<CheckResult>(`${root}/check`, { method: 'POST', body: {}, timeout: 12000 }),
  relay: (relay: RelayName, on: boolean) => request<CommandResult>(`${root}/relay`, { method: 'POST', body: { relay, on, confirm: true }, timeout: 12000 }),
  auto: (on: boolean) => request<CommandResult>(`${root}/auto`, { method: 'POST', body: { on, confirm: true }, timeout: 12000 }),
  limit: (name: LimitName, value: number) => request<CommandResult>(`${root}/limit`, { method: 'POST', body: { name, value, confirm: true }, timeout: 12000 }),
  estop: () => request<CommandResult>(`${root}/estop`, { method: 'POST', body: {}, timeout: 12000 }),
  resetAlarms: () => request<CommandResult>(`${root}/alarm/reset`, { method: 'POST', body: { confirm: true }, timeout: 12000 }),
  simulate: (what: SimulatorSwitch, on: boolean) => request<CommandResult>(`${root}/simulator`, { method: 'POST', body: { what, on }, timeout: 8000 }),
}
