// design-v3 hero illustration: our own line drawing of the reactor for a light «paper» card — black outline,
// lime accents, small ✦ sparkles. Live, from the four relays of the stand:
//   1 heat        warm glow under the substrate     2 cool (LEDs)   blue glow along the walls
//   3 mixer       the impeller turns                4 compressor    air/gas runs along the gas line
// Bubbles follow the gas indicator. A legend on the left says which relay is ON in words («вкл»), not colour alone.
// No link -> dashed, still, «Нет связи». Motion: transform/opacity/stroke-dashoffset only.
import type { CSSProperties, ReactNode } from 'react'
import { tr } from '../i18n'
import type { SceneState } from './useReactorLive'

const BUBBLES: [number, number, number, number, boolean][] = [   // x, r, duration s, delay s, lime
  [188, 7, 3.4, 0, true], [206, 4, 2.8, 1.1, false], [292, 9, 3.9, 2.2, false], [228, 5, 3.1, .6, true],
  [286, 6, 4.0, 1.7, false], [316, 4, 2.7, 2.9, true], [196, 5, 3.6, .3, false], [308, 8, 3.3, 3.4, true],
]
const num = (v: number | null, digits = 0) => v == null ? '—' : v.toFixed(digits)

function LegendRow({ y, on, label, children }: { y: number; on: boolean; label: string; children: ReactNode }) {
  return <g className={`lr-legend ${on ? 'is-on' : ''}`} transform={`translate(10 ${y})`}>
    <rect className="lr-legend-bg" x="0" y="-18" width="146" height="36" rx="18" />
    <g className="lr-legend-icon" transform="translate(10 -9)">{children}</g>
    <text className="lr-legend-text" x="33" y={on ? -1 : 5}>{label}</text>
    {on && <text className="lr-legend-on" x="33" y="13">{tr('v3.on')}</text>}
  </g>
}

export function LineReactor({ s }: { s: SceneState }) {
  const r = s.relays
  return <svg className={`lr ${s.live ? 'is-live' : 'is-offline'}`} viewBox="0 0 460 400" role="img" aria-label={tr('ov.scene')}>
    <defs>
      <clipPath id="lr-barrel"><rect x="170" y="100" width="170" height="242" rx="34" /></clipPath>
    </defs>
    {/* sparkles: decoration only */}
    <g className="lr-sparkles" aria-hidden="true">
      <path className="lr-sparkle s1" d="M150 34c.8 6 4.6 10 11.4 11.4-6.8 1.4-10.6 5.4-11.4 11.4-.8-6-4.6-10-11.4-11.4C145.4 44 149.2 40 150 34Z" />
      <path className="lr-sparkle s2" d="M440 104c.5 3.8 2.9 6.3 7.2 7.2-4.3.9-6.7 3.4-7.2 7.2-.5-3.8-2.9-6.3-7.2-7.2 4.3-.9 6.7-3.4 7.2-7.2Z" />
      <path className="lr-sparkle s3" d="M150 352c.5 3.8 2.9 6.3 7.2 7.2-4.3.9-6.7 3.4-7.2 7.2-.5-3.8-2.9-6.3-7.2-7.2 4.3-.9 6.7-3.4 7.2-7.2Z" />
    </g>
    {/* relay 1: warm glow under the reactor */}
    <ellipse className={`lr-heat-glow ${r.heat ? 'is-on' : ''}`} cx="255" cy="336" rx="112" ry="30" />
    {/* relay 2: cooling LEDs along the walls, blue glow when on */}
    <g className={`lr-cool ${r.cool ? 'is-on' : ''}`}>
      <rect className="lr-cool-glow" x="156" y="140" width="198" height="170" rx="40" />
      <path className="lr-cool-line" d="M162 150 V 300 M348 150 V 300" />
      {[170, 210, 250, 290].map(y => <g key={y}><circle cx="162" cy={y} r="4" /><circle cx="348" cy={y} r="4" /></g>)}
    </g>
    {/* substrate inside the barrel */}
    <g clipPath="url(#lr-barrel)">
      <path className="lr-substrate" d="M150 160 q 24 -10 48 0 t 48 0 t 48 0 t 48 0 t 48 0 V 360 H 150 Z" />
      <g className={`lr-bubbles rate-${s.rate}`}>
        {BUBBLES.map(([x, rad, dur, delay, lime], i) => <circle key={i} className={`lr-bubble ${lime ? 'is-lime' : ''}`} cx={x} cy={318} r={rad}
          style={{ animationDuration: `${dur}s`, animationDelay: `${delay}s` } as CSSProperties} />)}
      </g>
      <path className={`lr-heater ${r.heat ? 'is-on' : ''}`} d="M182 330 l 12 -9 l 12 9 l 12 -9 l 12 9 l 12 -9 l 12 9 l 12 -9 l 12 9 l 12 -9 l 12 9 l 12 -9 l 12 9" />
      {/* relay 3: the mixer — shaft from the motor, impeller in the substrate */}
      <path className="lr-line" d="M255 60 V 262" />
      <g className={`lr-impeller ${r.mixer ? 'is-on' : ''}`}>
        <path className="lr-line lr-blade" d="M255 268 l 28 -7 q 5 7 0 14 Z M255 268 l -28 7 q -5 -7 0 -14 Z" />
        <circle className="lr-dot" cx="255" cy="268" r="5" />
      </g>
    </g>
    <rect className="lr-line lr-barrel" x="170" y="100" width="170" height="242" rx="34" />
    <path className="lr-line lr-thin" d="M170 160 H 340" strokeDasharray="5 6" />
    {/* mixer motor on the lid */}
    <rect className={`lr-line lr-motor ${r.mixer ? 'is-on' : ''}`} x="237" y="40" width="36" height="22" rx="5" />
    {/* legs and ground */}
    <path className="lr-line" d="M196 342 v 26 M314 342 v 26 M150 368 H 452" />
    {/* temperature probe */}
    <path className="lr-line" d="M340 300 H 350" /><circle className="lr-dot" cx="352" cy="300" r="5" />
    <text className="lr-label" x="362" y="296">{tr('ov.temp')}</text>
    <text className="lr-value" x="362" y="320">{num(s.temp, 1)} °C</text>
    {/* relay 4: compressor on the gas line -> gas holder; the flow runs only while it is ON */}
    <g className={`lr-pipe ${r.compressor ? 'is-flowing' : ''}`}>
      <path className="lr-line" d="M305 100 V 76 H 406 V 132" />
      <path className="lr-flow" d="M305 100 V 76 H 406 V 132" />
    </g>
    <g className={`lr-compressor ${r.compressor ? 'is-on' : ''}`}>
      <rect className="lr-line lr-comp-body" x="334" y="62" width="44" height="28" rx="6" />
      <path className="lr-line lr-thin lr-comp-air" d="M342 70 h 10 M342 76 h 16 M342 82 h 8" />
    </g>
    <rect className="lr-line" x="380" y="156" width="54" height="84" rx="10" />
    <path className="lr-line lr-bell" d="M386 202 V 154 q 0 -22 21 -22 q 21 0 21 22 V 202" style={{ transform: `translateY(${(-(s.gas * 20)).toFixed(1)}px)` }} />
    <text className="lr-label" x="407" y="262" textAnchor="middle">{tr('ov.holder')}</text>
    {/* legend: the four relays of the stand, ON said in words */}
    <LegendRow y={128} on={r.heat} label={tr('ov.heat')}>
      <path className="lr-ico" d="M8 1c3 4 6 6.5 6 10a6 6 0 0 1-12 0c0-2.4 1.4-4 3-5.4.4 1.7 1.3 2.6 2.4 3C7 6 7.6 3.6 8 1Z" />
    </LegendRow>
    <LegendRow y={178} on={r.cool} label={tr('ov.cool')}>
      <path className="lr-ico" d="M8 0v18M0.5 4.5l15 9M15.5 4.5l-15 9M5 1.5l3 2 3-2M5 16.5l3-2 3 2" />
    </LegendRow>
    <LegendRow y={228} on={r.mixer} label={tr('ov.mixer')}>
      <path className="lr-ico" d="M8 0v8M8 9l7-2.5q1.5 2.5 0 5L8 9Zm0 0-7 2.5q-1.5-2.5 0-5L8 9Z" />
    </LegendRow>
    <LegendRow y={278} on={r.compressor} label={tr('ov.auger')}>
      <path className="lr-ico" d="M1 5h10a3 3 0 1 0-3-3M1 10h14a3 3 0 1 1-3 3M1 15h6" />
    </LegendRow>
    {!s.live && <g className="lr-nolink" role="status"><rect x="170" y="190" width="170" height="48" rx="10" /><text x="255" y="221" textAnchor="middle">{tr('ov.noLink')}</text></g>}
  </svg>
}
