// A /api/reactor/status answer for tests (the shape of src/hardware/client.py status()).
import type { ReactorStatus } from '../src/reactorApi'

export function reactorStatus(over: Partial<ReactorStatus> = {}, relays: Partial<Record<'heat' | 'cool' | 'pump', Partial<ReactorStatus['relays']['heat']>>> = {}): ReactorStatus {
  const relay = (name: 'heat' | 'cool' | 'pump') => ({ on: false, on_for_s: 0, total_s: 0, on_blocked: null, ...relays[name] })
  return {
    source: { kind: 'simulator', address: null, arduino_port: 'virtual', firmware: 'virtual-0.1' },
    link: { ok: true, level: null, network_ok: true, arduino_ok: true, seconds_since_pi: 0.4, error: null },
    readings: {
      temp_c: { value: 31.2, last: 31.2, level: 'warn' }, rh_pct: { value: 87.4, last: 87.4, level: 'ok' },
      gas_in: { value: 432, last: 432, level: 'ok' }, gas_out: { value: 78, last: 78, level: 'ok' },
      p_kpa: { value: 1.25, last: 1.25, level: 'ok', fill_share: 0.357 },
    },
    relays: { heat: relay('heat'), cool: relay('cool'), pump: relay('pump') },
    alarms: [], leak_latched: false, overheat: false, controls_enabled: true,
    thresholds: {
      temp_c: { target: 37, danger_low: 25, warn_low: 33, warn_high: 40, danger_high: 43 }, overheat_c: 45, overheat_release_c: 43,
      rh_pct: { warn_high: 95, danger_high: 99 }, gas_in_raw: { warn_low: 150 }, gas_out_raw: { warn: 300, leak: 400 },
      pressure_kpa: { pump_warn: 2, danger: 3, scale_max: 3.5, pump_stop: 0.1 },
    },
    laptop_watchdog: { timeout_s: 15, seconds_since_laptop: 0.4, ok: true },
    simulator: { leak: false, usb: false, arduino_silent: false, temp_sensor: false, network: false },
    time: 1_763_440_000,
    ...over,
  }
}
