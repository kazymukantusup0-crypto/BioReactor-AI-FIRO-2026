// A /api/reactor/status answer for tests (the shape of src/hardware/client.py status(), firmware bioreactor-1.0).
import type { RelayName, ReactorStatus } from '../src/reactorApi'

export const NO_ALARMS = { estop: false, leak: false, overheat: false, warmup: false, no_temp: false, link_lost: false, auger_timeout: false }

export function reactorStatus(over: Partial<ReactorStatus> = {}, relays: Partial<Record<RelayName, Partial<ReactorStatus['relays']['heat']>>> = {}): ReactorStatus {
  const relay = (name: RelayName) => ({ on: false, remote: false, on_for_s: 0, total_s: 0, on_blocked: null, ...relays[name] })
  return {
    source: { kind: 'simulator', mode: 'simulator', address: null, route: null, arduino_port: 'virtual', firmware: 'bioreactor-1.0-virtual' },
    link: { ok: true, level: null, network_ok: true, arduino_ok: true, seconds_since_pi: 0.4, error: null },
    readings: {
      temp_c: { value: 31.2, last: 31.2, level: 'warn' }, rh_pct: { value: 87.4, last: 87.4, level: 'ok' },
      gas_in: { value: 432, last: 432, level: 'ok' }, gas_out: { value: 78, last: 78, level: 'ok' },
    },
    relays: { heat: relay('heat'), cool: relay('cool'), pump: relay('pump'), auger: relay('auger') },
    alarms: [], auto: false,
    limits: { temp_min: 35, temp_max: 38, temp_hard_max: 45, gas_out_limit: 400, gas_in_limit: 700 },
    arduino_alarms: { ...NO_ALARMS },
    controls_enabled: true, estop_enabled: true,
    laptop_watchdog: { timeout_s: 15, seconds_since_laptop: 0.4, ok: true },
    simulator: { leak: false, usb: false, arduino_silent: false, temp_sensor: false, network: false },
    time: 1_763_440_000,
    ...over,
  }
}
