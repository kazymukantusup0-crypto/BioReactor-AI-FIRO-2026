// «Реактор» page API: Arduino -> USB -> Raspberry Pi -> network -> laptop server (/api/reactor/*).
import { request } from './api'

export type Level = 'ok' | 'warn' | 'danger' | 'unknown'
export type RelayName = 'heat' | 'cool' | 'pump'
export type SensorName = 'temp_c' | 'rh_pct' | 'gas_in' | 'gas_out' | 'p_kpa'
export const RELAYS: RelayName[] = ['heat', 'cool', 'pump']
export const SENSORS: SensorName[] = ['temp_c', 'rh_pct', 'gas_in', 'gas_out', 'p_kpa']

export interface Reading { value: number | null; last: number | null; level: Level; fill_share?: number | null }
export interface RelayState { on: boolean; on_for_s: number; total_s: number; on_blocked: string | null }
export interface Alarm { code: string; level: Level; needs_reset?: boolean; still_leaking?: boolean; since?: number; error?: string | null }
export interface Thresholds {
  temp_c: { target: number; danger_low: number; warn_low: number; warn_high: number; danger_high: number }
  overheat_c: number; overheat_release_c: number
  rh_pct: { warn_high: number; danger_high: number }
  gas_in_raw: { warn_low: number }
  gas_out_raw: { warn: number; leak: number }
  pressure_kpa: { pump_warn: number; danger: number; scale_max: number; pump_stop: number }
}
export interface ReactorStatus {
  source: { kind: 'simulator' | 'pi'; address: string | null; arduino_port: string | null; firmware: string | null }
  link: { ok: boolean; level: 'pi' | 'arduino' | null; network_ok: boolean; arduino_ok: boolean; seconds_since_pi: number | null; error: string | null }
  readings: Record<SensorName, Reading>
  relays: Record<RelayName, RelayState>
  alarms: Alarm[]
  leak_latched: boolean
  overheat: boolean
  controls_enabled: boolean
  thresholds: Thresholds | null
  laptop_watchdog: { timeout_s: number; seconds_since_laptop: number; ok: boolean } | null
  simulator: Record<string, boolean> | null
  time: number
}
export interface HistoryPoint { t: number; temp_c: number | null; rh_pct: number | null; gas_in: number | null; gas_out: number | null; p_kpa: number | null; relay_heat: number; relay_cool: number; relay_pump: number }
export interface JournalItem { id: number; ts: string; kind: string; what: string; who: string; result: string | null; source: string; details: Record<string, unknown> }
export interface CommandResult { ok: boolean; reason: string | null; relays?: Record<RelayName, boolean>; error?: string }
export interface CheckResult { ok: boolean; url: string; mode: string; latency_ms: number; arduino_ok?: boolean; port?: string | null; firmware?: string | null; simulated?: boolean; error?: string }
export type SimulatorSwitch = 'leak' | 'usb' | 'arduino_silent' | 'temp_sensor' | 'network'

const root = '/api/reactor'
export const reactorApi = {
  status: (signal?: AbortSignal) => request<ReactorStatus>(`${root}/status`, { signal, timeout: 5000 }),
  history: (window: 600 | 3600, signal?: AbortSignal) => request<{ window: number; points: HistoryPoint[]; live: boolean }>(`${root}/history?window=${window}`, { signal, timeout: 8000 }),
  journal: (signal?: AbortSignal) => request<{ items: JournalItem[]; live: boolean }>(`${root}/journal?limit=40`, { signal, timeout: 8000 }),
  check: () => request<CheckResult>(`${root}/check`, { method: 'POST', body: {}, timeout: 8000 }),
  relay: (relay: RelayName, on: boolean) => request<CommandResult>(`${root}/relay`, { method: 'POST', body: { relay, on, confirm: true }, timeout: 12000 }),
  resetLeak: () => request<CommandResult>(`${root}/alarm/reset`, { method: 'POST', body: { confirm: true }, timeout: 12000 }),
  simulate: (what: SimulatorSwitch, on: boolean) => request<CommandResult>(`${root}/simulator`, { method: 'POST', body: { what, on }, timeout: 8000 }),
}
