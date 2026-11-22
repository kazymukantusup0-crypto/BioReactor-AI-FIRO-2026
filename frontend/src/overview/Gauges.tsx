// Instrument readouts of «Обзор»: an arc gauge with the normal corridor (temperature), a ring with the pump
// threshold (gas indicator) and a big number with a range (methane). Status is a word + an icon, never colour alone.
// The value arc moves with stroke-dashoffset (one property, compositor-friendly enough for 1 update per second).
import { AlertTriangle, CheckCircle2, HelpCircle, XCircle } from 'lucide-react'
import type { Level } from '../reactorApi'
import { tr } from '../i18n'

const LEVEL_ICON = { ok: CheckCircle2, warn: AlertTriangle, danger: XCircle, unknown: HelpCircle } as const

export function LevelWord({ level }: { level: Level }) {
  const Icon = LEVEL_ICON[level]
  return <span className={`ov-level ov-level-${level}`}><Icon size={16} aria-hidden="true" />{tr(`ov.level.${level}`)}</span>
}

// Arc geometry: 240° sweep, opening at the bottom
const R = 78, CX = 100, CY = 100, SWEEP = 240, START = 150
const polar = (deg: number) => { const a = (deg * Math.PI) / 180; return [CX + R * Math.cos(a), CY + R * Math.sin(a)] }
const arc = (from: number, to: number) => { const [x1, y1] = polar(from), [x2, y2] = polar(to); return `M ${x1.toFixed(2)} ${y1.toFixed(2)} A ${R} ${R} 0 ${to - from > 180 ? 1 : 0} 1 ${x2.toFixed(2)} ${y2.toFixed(2)}` }
const LENGTH = (2 * Math.PI * R * SWEEP) / 360
const frac = (v: number, min: number, max: number) => Math.min(1, Math.max(0, (v - min) / (max - min)))

export function ArcGauge({ value, min, max, band, mark, unit, label, level, digits = 1, testId }: {
  value: number | null; min: number; max: number; band?: [number, number] | null; mark?: number | null
  unit: string; label: string; level: Level; digits?: number; testId?: string
}) {
  const f = value == null ? 0 : frac(value, min, max)
  return <figure className={`ov-gauge ov-gauge-${level}`} data-testid={testId}>
    <svg viewBox="0 0 200 172" aria-hidden="true">
      <path className="ov-gauge-track" d={arc(START, START + SWEEP)} />
      {band && <path className="ov-gauge-band" d={arc(START + SWEEP * frac(band[0], min, max), START + SWEEP * frac(band[1], min, max))} />}
      <path className="ov-gauge-value" d={arc(START, START + SWEEP)} style={{ strokeDasharray: LENGTH, strokeDashoffset: LENGTH * (1 - f) }} />
      {mark != null && (() => { const a = START + SWEEP * frac(mark, min, max); const [x1, y1] = polar(a); const k = (R + 12) / R
        return <line className="ov-gauge-mark" x1={x1} y1={y1} x2={CX + (x1 - CX) * k} y2={CY + (y1 - CY) * k} /> })()}
    </svg>
    <div className="ov-gauge-readout">
      <span className="ov-gauge-number ds-num">{value == null ? '—' : value.toFixed(digits)}</span>
      <span className="ov-gauge-unit">{unit}</span>
    </div>
    <figcaption><span className="ov-gauge-label">{label}</span><LevelWord level={level} /></figcaption>
  </figure>
}

export function BigNumber({ label, value, unit, sub, level }: { label: string; value: string; unit: string; sub: string; level: Level }) {
  return <figure className={`ov-big ov-big-${level}`}>
    <figcaption className="ov-gauge-label">{label}</figcaption>
    <div className="ov-big-readout"><span className="ov-big-number ds-num">{value}</span><span className="ov-gauge-unit">{unit}</span></div>
    <p className="ov-big-sub">{sub}</p>
  </figure>
}
