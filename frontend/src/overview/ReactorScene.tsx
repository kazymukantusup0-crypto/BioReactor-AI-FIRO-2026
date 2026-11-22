// The live reactor drawing of «Обзор». Two layouts share the same parts:
//   cutaway  the barrel large, drawn like an engineering sheet (dimension lines, sensor call-outs), gas holder beside
//   process  the chain feed -> auger -> reactor -> gas holder -> pump -> consumer, left to right
// Everything is driven by the real status: substrate colour by temperature (--heat 0..1), bubbles by the gas
// indicator, the gas holder bell by gas / pump threshold, relay parts light up only when that relay is ON.
// No link -> the scene is grey, still, and says «Нет связи». Motion: CSS transform/opacity/stroke-dashoffset only
// (compositor-friendly), paused off-screen by the browser; reduced motion -> no movement (overview.css).
import type { CSSProperties } from 'react'
import type { ReactorStatus } from '../reactorApi'
import { tr } from '../i18n'
import { bubbleRate, gasShare, heatOf } from './useReactorLive'

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

const num = (v: number | null, digits = 0) => v == null ? '—' : v.toFixed(digits)

// bubbles: x across the vessel, size, duration (s), delay (s) — fixed, so the pattern is stable between renders
const BUBBLES: [number, number, number, number][] = [
  [0.14, 5, 3.4, 0], [0.27, 3, 2.8, 1.1], [0.36, 6, 3.9, 2.2], [0.48, 4, 3.1, 0.6], [0.57, 7, 4.0, 1.7],
  [0.66, 3, 2.7, 2.9], [0.74, 5, 3.6, 0.3], [0.83, 4, 3.0, 1.4], [0.22, 4, 3.7, 3.1], [0.62, 5, 3.3, 3.6],
  [0.42, 3, 2.9, 0.9], [0.79, 6, 3.8, 2.5],
]

/** Substrate, bubbles, heater coil and probes inside a vessel box (x, y, w, h) with a working level 0..1. */
function Vessel({ x, y, w, h, level, s, clipId }: { x: number; y: number; w: number; h: number; level: number; s: SceneState; clipId: string }) {
  const top = y + h * (1 - level)
  const rise = top - (y + h) + 18
  return <g className="rs-vessel">
    <clipPath id={clipId}><rect x={x} y={y} width={w} height={h} rx={Math.min(28, w * 0.12)} /></clipPath>
    <rect className="rs-vessel-body" x={x} y={y} width={w} height={h} rx={Math.min(28, w * 0.12)} />
    <g clipPath={`url(#${clipId})`}>
      <rect className="rs-headspace" x={x} y={y} width={w} height={top - y} />
      {/* substrate with a slow surface wave (the wave path is wider than the vessel and drifts sideways) */}
      <g className="rs-substrate">
        <rect className="rs-substrate-fill" x={x} y={top + 6} width={w} height={y + h - top} />
        <path className="rs-wave" d={`M ${x - w} ${top + 6} q ${w / 8} -9 ${w / 4} 0 t ${w / 4} 0 t ${w / 4} 0 t ${w / 4} 0 t ${w / 4} 0 t ${w / 4} 0 t ${w / 4} 0 t ${w / 4} 0 V ${top + 14} H ${x - w} Z`} />
      </g>
      <g className={`rs-bubbles rate-${s.rate}`} aria-hidden="true">
        {BUBBLES.map(([fx, r, dur, delay], i) => <circle key={i} className="rs-bubble" cx={x + w * fx} cy={y + h - 14} r={r}
          style={{ '--rise': `${rise}px`, animationDuration: `${dur}s`, animationDelay: `${delay}s` } as CSSProperties} />)}
      </g>
      {/* heater coil at the bottom */}
      <path className={`rs-heater ${s.relays.heat ? 'is-on' : ''}`} d={`M ${x + w * 0.12} ${y + h - 22} ${Array.from({ length: 9 }, (_, i) => `l ${w * 0.085} ${i % 2 ? -10 : 10}`).join(' ')}`} />
    </g>
    <rect className="rs-vessel-rim" x={x} y={y} width={w} height={h} rx={Math.min(28, w * 0.12)} />
    {/* cooling jacket: two vertical lines along the walls */}
    <g className={`rs-cool ${s.relays.cool ? 'is-on' : ''}`}>
      <line x1={x - 9} y1={y + 30} x2={x - 9} y2={y + h - 30} /><line x1={x + w + 9} y1={y + 30} x2={x + w + 9} y2={y + h - 30} />
    </g>
  </g>
}

/** The gas holder: a water tank and a bell that rises with the gas (transform only). */
function GasHolder({ x, y, w, h, s }: { x: number; y: number; w: number; h: number; s: SceneState }) {
  const travel = h * 0.42
  return <g className="rs-holder">
    <rect className="rs-holder-tank" x={x} y={y + h * 0.4} width={w} height={h * 0.6} rx={10} />
    <g className="rs-bell" style={{ transform: `translateY(${-(s.gas * travel).toFixed(1)}px)` }}>
      <path className="rs-bell-body" d={`M ${x + 10} ${y + h * 0.82} V ${y + h * 0.42} q 0 -26 ${w / 2 - 10} -26 q ${w / 2 - 10} 0 ${w / 2 - 10} 26 V ${y + h * 0.82} Z`} />
    </g>
    <rect className="rs-holder-water" x={x + 3} y={y + h * 0.62} width={w - 6} height={h * 0.38 - 3} rx={8} />
  </g>
}

/** A pump: a circle with an impeller that turns while the pump relay is on. */
function Pump({ cx, cy, s }: { cx: number; cy: number; s: SceneState }) {
  return <g className={`rs-pump ${s.relays.pump ? 'is-on' : ''}`}>
    <circle className="rs-pump-body" cx={cx} cy={cy} r={17} />
    <g className="rs-impeller" style={{ transformOrigin: `${cx}px ${cy}px` }}>
      <path d={`M ${cx} ${cy - 11} L ${cx} ${cy + 11} M ${cx - 11} ${cy} L ${cx + 11} ${cy} M ${cx - 8} ${cy - 8} L ${cx + 8} ${cy + 8} M ${cx - 8} ${cy + 8} L ${cx + 8} ${cy - 8}`} />
    </g>
  </g>
}

/** The auger: a shaft with flights that move while the auger relay is on. */
function Auger({ x, y, w, s, clipId }: { x: number; y: number; w: number; s: SceneState; clipId: string }) {
  return <g className={`rs-auger ${s.relays.auger ? 'is-on' : ''}`}>
    <clipPath id={clipId}><rect x={x} y={y - 12} width={w} height={24} rx={6} /></clipPath>
    <rect className="rs-auger-tube" x={x} y={y - 12} width={w} height={24} rx={6} />
    <g clipPath={`url(#${clipId})`}><path className="rs-auger-flights" d={Array.from({ length: Math.ceil(w / 14) + 3 }, (_, i) => `M ${x - 28 + i * 14} ${y + 10} l 10 -20`).join(' ')} /></g>
  </g>
}

function Pipe({ d, flowing }: { d: string; flowing: boolean }) {
  return <g className={`rs-pipe ${flowing ? 'is-flowing' : ''}`}><path className="rs-pipe-line" d={d} /><path className="rs-pipe-flow" d={d} /></g>
}

function Tag({ x, y, label, value, tone = '' }: { x: number; y: number; label: string; value: string; tone?: string }) {
  return <g className={`rs-tag ${tone}`} transform={`translate(${x} ${y})`}>
    <text className="rs-tag-label" y={0}>{label}</text>
    <text className="rs-tag-value" y={24}>{value}</text>
  </g>
}

function NoLink({ cx, cy }: { cx: number; cy: number }) {
  return <g className="rs-nolink" role="status">
    <rect x={cx - 112} y={cy - 30} width={224} height={60} rx={14} />
    <text x={cx} y={cy + 7} textAnchor="middle">{tr('ov.noLink')}</text>
  </g>
}

const sceneStyle = (s: SceneState) => ({ '--heat': s.heat.toFixed(3) } as CSSProperties)
const sceneClass = (s: SceneState, layout: string) => `rs ${layout} ${s.live ? 'is-live' : 'is-offline'} ${s.leak ? 'is-leak' : ''}`

/** Cutaway: viewBox 640×560. */
export function ReactorCutaway({ s }: { s: SceneState }) {
  const level = 0.8      // 160 L working of 200 L
  return <svg className={sceneClass(s, 'rs-cutaway')} style={sceneStyle(s)} viewBox="0 0 640 560" role="img" aria-label={tr('ov.scene')}>
    <ellipse className="rs-glow" cx={270} cy={330} rx={220} ry={210} />
    {/* dimension line: total volume */}
    <g className="rs-dim"><line x1={118} y1={90} x2={118} y2={470} /><line x1={110} y1={90} x2={126} y2={90} /><line x1={110} y1={470} x2={126} y2={470} />
      <text x={104} y={284} textAnchor="end">{tr('ov.liters', { v0: 200 })}</text></g>
    <Vessel x={150} y={90} w={240} h={380} level={level} s={s} clipId="rs-cut-clip" />
    <g className="rs-dim rs-dim-level"><line x1={140} y1={166} x2={400} y2={166} /><text x={136} y={186} textAnchor="end">{tr('ov.working', { v0: 160 })}</text></g>
    {/* gas line: reactor top -> pump -> gas holder */}
    <Pipe d="M 270 90 V 46 H 452 V 250" flowing={s.relays.pump} />
    <Pump cx={392} cy={46} s={s} />
    <GasHolder x={470} y={210} w={130} h={260} s={s} />
    <Pipe d="M 452 250 H 470" flowing={s.relays.pump} />
    {/* feed: hopper + auger into the bottom */}
    <path className="rs-hopper" d="M 22 352 H 112 L 92 404 H 42 Z" />
    <Auger x={56} y={430} w={96} s={s} clipId="rs-cut-auger" />
    {/* probes and call-outs */}
    <g className="rs-probe"><line x1={390} y1={340} x2={330} y2={340} /><circle cx={330} cy={340} r={4} /></g>
    <line className="rs-leader" x1={392} y1={340} x2={430} y2={372} />
    <Tag x={434} y={368} label={tr('ov.temp')} value={`${num(s.temp, 1)} °C`} />
    <g className="rs-probe"><circle cx={190} cy={122} r={5} /></g>
    <line className="rs-leader" x1={186} y1={118} x2={150} y2={60} />
    <Tag x={10} y={36} label={tr('ov.gasIn')} value={`${num(s.gasIn)} / 1023`} />
    <g className={`rs-probe rs-leak-probe ${s.leak ? 'is-alarm' : ''}`}><circle cx={430} cy={500} r={5} /></g>
    <Tag x={444} y={498} label={tr('ov.gasOut')} value={`${num(s.gasOut)} / 1023`} tone={s.leak ? 'is-alarm' : ''} />
    <text className="rs-caption" x={535} y={200} textAnchor="middle">{tr('ov.holder')}</text>
    <line className="rs-ground" x1={0} y1={520} x2={640} y2={520} />
    {!s.live && <NoLink cx={270} cy={300} />}
  </svg>
}

/** Process: viewBox 1200×440. */
export function ReactorProcess({ s }: { s: SceneState }) {
  return <svg className={sceneClass(s, 'rs-process')} style={sceneStyle(s)} viewBox="0 10 1200 410" role="img" aria-label={tr('ov.scene')}>
    <ellipse className="rs-glow" cx={500} cy={236} rx={300} ry={190} />
    {/* 1. feed */}
    <path className="rs-hopper" d="M 40 196 H 160 L 134 262 H 66 Z" />
    <text className="rs-caption" x={100} y={180} textAnchor="middle">{tr('ov.feed')}</text>
    <Auger x={100} y={300} w={230} s={s} clipId="rs-proc-auger" />
    <text className="rs-caption rs-caption-sm" x={200} y={344} textAnchor="middle">{tr('ov.auger')}</text>
    {/* 2. reactor */}
    <Vessel x={330} y={70} w={340} h={300} level={0.8} s={s} clipId="rs-proc-clip" />
    <text className="rs-caption" x={500} y={404} textAnchor="middle">{tr('ov.reactor', { v0: 200, v1: 160 })}</text>
    {/* 3. gas line -> pump -> holder -> consumer */}
    <Pipe d="M 500 70 V 36 H 820 V 150" flowing={s.relays.pump} />
    <Pump cx={700} cy={36} s={s} />
    <GasHolder x={760} y={120} w={140} h={250} s={s} />
    <text className="rs-caption" x={830} y={404} textAnchor="middle">{tr('ov.holder')}</text>
    <Pipe d="M 900 300 H 1040" flowing={s.relays.pump} />
    <g className={`rs-flame ${s.relays.pump ? 'is-on' : ''}`}>
      <path className="rs-flame-outer" d="M 1100 262 q -30 -40 0 -84 q 30 44 0 84 Z" />
      <path className="rs-flame-inner" d="M 1100 262 q -14 -22 0 -46 q 14 24 0 46 Z" />
      <rect className="rs-burner" x={1050} y={268} width={100} height={18} rx={6} />
    </g>
    <text className="rs-caption" x={1100} y={330} textAnchor="middle">{tr('ov.consumer')}</text>
    {/* call-outs */}
    <Tag x={350} y={420 - 300} label={tr('ov.temp')} value={`${num(s.temp, 1)} °C`} />
    <Tag x={556} y={120} label={tr('ov.gasIn')} value={`${num(s.gasIn)} / 1023`} />
    <Tag x={930} y={190} label={tr('ov.gasOut')} value={`${num(s.gasOut)} / 1023`} tone={s.leak ? 'is-alarm' : ''} />
    {!s.live && <NoLink cx={500} cy={220} />}
  </svg>
}
