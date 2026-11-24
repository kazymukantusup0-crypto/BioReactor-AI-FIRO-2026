// Live data for the «Обзор» scene: the reactor status every second (only while the tab is visible) and one methane
// estimate for the demo reactor from the same calculation as the «Сырьё и смеси» page. Read-only: nothing is switched.
import { useEffect, useState } from 'react'
import { reactorApi, type ReactorStatus } from '../reactorApi'
import { substratesApi, type EstimateData } from '../substratesApi'
import { getLang } from '../i18n'

// The demo reactor (data/config/demo_reactor.json): a 200 L barrel, 160 L working volume, cattle slurry.
export const DEMO_REACTOR = { volume_l: 200, working_l: 160, material: 'cattle_manure' } as const

export interface LiveReactor { status: ReactorStatus | null; failed: boolean; methane: EstimateData | null }

export function useReactorLive(): LiveReactor {
  const [status, setStatus] = useState<ReactorStatus | null>(null)
  const [failed, setFailed] = useState(false)
  const [methane, setMethane] = useState<EstimateData | null>(null)

  useEffect(() => {
    let alive = true
    let timer: ReturnType<typeof setTimeout> | undefined
    const controller = new AbortController()
    const tick = async () => {
      if (document.visibilityState === 'visible') {
        try { const value = await reactorApi.status(controller.signal); if (alive) { setStatus(value); setFailed(false) } }
        catch { if (alive) setFailed(true) }
      }
      if (alive) timer = setTimeout(tick, 1000)
    }
    tick()
    return () => { alive = false; controller.abort(); if (timer) clearTimeout(timer) }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    substratesApi.estimate([{ material: DEMO_REACTOR.material, quantity: DEMO_REACTOR.working_l, unit: 'L' }], getLang(), controller.signal)
      .then(result => { if (result.ok) setMethane(result.data) })
      .catch(() => { /* the scene shows «—» */ })
    return () => controller.abort()
  }, [])

  return { status, failed, methane }
}

/** 0 cold … 1 hot, for the substrate colour: 5 °C blue, ~20 °C green, the working 35–38 °C warm amber (5 °C … 40 °C). */
export function heatOf(temp: number | null | undefined): number {
  if (temp == null || Number.isNaN(temp)) return 0.35
  return Math.min(1, Math.max(0, (temp - 5) / 35))
}

/** The gas indicator 0–1023 as a share of the pump threshold (the bell of the gas holder rises with it). */
export function gasShare(raw: number | null | undefined, threshold: number | null | undefined): number {
  if (raw == null) return 0
  return Math.min(1, Math.max(0, raw / (threshold && threshold > 0 ? threshold : 1023)))
}

/** Bubble rate bucket from the gas indicator: still, low, mid, high. Buckets change rarely, so loops do not restart. */
export function bubbleRate(raw: number | null | undefined, live: boolean): 'still' | 'low' | 'mid' | 'high' {
  if (!live || raw == null) return 'still'
  return raw < 250 ? 'low' : raw < 550 ? 'mid' : 'high'
}

/** What the reactor drawing needs, from the status: everything stays still and grey without a link. */
export interface SceneState {
  live: boolean            // link ok and readings fresh
  simulated: boolean
  temp: number | null
  gasIn: number | null
  gasOut: number | null
  heat: number             // 0..1
  gas: number              // 0..1 of the pump threshold
  rate: 'still' | 'low' | 'mid' | 'high'
  relays: { heat: boolean; cool: boolean; pump: boolean; auger: boolean }
  leak: boolean
}

export function sceneState(status: ReactorStatus | null): SceneState {
  const live = Boolean(status?.link.ok)
  const r = status?.readings
  const temp = r?.temp_c.value ?? null
  const gasIn = r?.gas_in.value ?? null
  return {
    live, simulated: status?.source.kind === 'simulator',
    temp, gasIn, gasOut: r?.gas_out.value ?? null,
    heat: heatOf(live ? temp : null),
    gas: live ? gasShare(gasIn, status?.limits?.gas_in_limit) : 0,
    rate: bubbleRate(gasIn, live),
    relays: { heat: live && Boolean(status?.relays.heat.on), cool: live && Boolean(status?.relays.cool.on),
              pump: live && Boolean(status?.relays.pump.on), auger: live && Boolean(status?.relays.auger.on) },
    leak: Boolean(status?.arduino_alarms?.leak),
  }
}

