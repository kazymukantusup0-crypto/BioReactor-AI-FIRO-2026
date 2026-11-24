// design-v3 hero illustration: our own line drawing of the reactor for a light «paper» card — black outline,
// lime accents, small ✦ sparkles. It is live: bubbles follow the gas indicator, the heater coil turns lime and the
// pump turns only while that relay is ON; no link -> dashed, still, «Нет связи». Motion: transform/opacity only.
import type { CSSProperties } from 'react'
import { tr } from '../i18n'
import type { SceneState } from './useReactorLive'

const BUBBLES: [number, number, number, number, boolean][] = [   // x, r, duration s, delay s, lime
  [168, 7, 3.4, 0, true], [196, 4, 2.8, 1.1, false], [222, 9, 3.9, 2.2, false], [250, 5, 3.1, .6, true],
  [276, 6, 4.0, 1.7, false], [300, 4, 2.7, 2.9, true], [186, 5, 3.6, .3, false], [262, 8, 3.3, 3.4, true],
]
const num = (v: number | null, digits = 0) => v == null ? '—' : v.toFixed(digits)

export function LineReactor({ s }: { s: SceneState }) {
  return <svg className={`lr ${s.live ? 'is-live' : 'is-offline'}`} viewBox="0 0 460 400" role="img" aria-label={tr('ov.scene')}>
    <defs><clipPath id="lr-barrel"><rect x="140" y="92" width="190" height="250" rx="34" /></clipPath></defs>
    {/* sparkles: decoration only */}
    <g className="lr-sparkles" aria-hidden="true">
      <path className="lr-sparkle s1" d="M58 70c.8 6 4.6 10 11.4 11.4-6.8 1.4-10.6 5.4-11.4 11.4-.8-6-4.6-10-11.4-11.4C53.4 80 57.2 76 58 70Z" />
      <path className="lr-sparkle s2" d="M404 40c.5 3.8 2.9 6.3 7.2 7.2-4.3.9-6.7 3.4-7.2 7.2-.5-3.8-2.9-6.3-7.2-7.2 4.3-.9 6.7-3.4 7.2-7.2Z" />
      <path className="lr-sparkle s3" d="M92 300c.5 3.8 2.9 6.3 7.2 7.2-4.3.9-6.7 3.4-7.2 7.2-.5-3.8-2.9-6.3-7.2-7.2 4.3-.9 6.7-3.4 7.2-7.2Z" />
    </g>
    {/* substrate inside the barrel */}
    <g clipPath="url(#lr-barrel)">
      <path className="lr-substrate" d="M120 152 q 24 -10 48 0 t 48 0 t 48 0 t 48 0 t 48 0 V 360 H 120 Z" />
      <g className={`lr-bubbles rate-${s.rate}`}>
        {BUBBLES.map(([x, r, dur, delay, lime], i) => <circle key={i} className={`lr-bubble ${lime ? 'is-lime' : ''}`} cx={x} cy={318} r={r}
          style={{ animationDuration: `${dur}s`, animationDelay: `${delay}s` } as CSSProperties} />)}
      </g>
      <path className={`lr-heater ${s.relays.heat ? 'is-on' : ''}`} d="M158 326 l 14 -10 l 14 10 l 14 -10 l 14 10 l 14 -10 l 14 10 l 14 -10 l 14 10 l 14 -10 l 14 10 l 14 -10" />
    </g>
    <rect className="lr-line lr-barrel" x="140" y="92" width="190" height="250" rx="34" />
    <path className="lr-line lr-thin" d="M140 152 H 330" strokeDasharray="5 6" />
    {/* legs and ground */}
    <path className="lr-line" d="M168 342 v 26 M302 342 v 26 M120 368 H 420" />
    {/* temperature probe */}
    <path className="lr-line" d="M330 300 H 340" /><circle className="lr-dot" cx="342" cy="300" r="5" />
    <text className="lr-label" x="352" y="296">{tr('ov.temp')}</text>
    <text className="lr-value" x="352" y="320">{num(s.temp, 1)} °C</text>
    {/* gas line, pump, gas holder */}
    <path className="lr-line" d="M235 92 V 54 H 372 V 128" />
    <g className={`lr-pump ${s.relays.pump ? 'is-on' : ''}`}>
      <circle className="lr-line lr-pump-body" cx="300" cy="54" r="15" />
      <g className="lr-impeller"><path className="lr-line" d="M300 44v20M290 54h20" /></g>
    </g>
    <rect className="lr-line" x="344" y="152" width="56" height="88" rx="10" />
    <path className="lr-line lr-bell" d="M350 200 V 150 q 0 -22 22 -22 q 22 0 22 22 V 200" style={{ transform: `translateY(${(-(s.gas * 20)).toFixed(1)}px)` }} />
    <text className="lr-label" x="344" y="262">{tr('ov.holder')}</text>
    {/* feed: hopper and auger */}
    <path className="lr-line" d="M36 214 H 104 L 90 252 H 50 Z" />
    <g className={`lr-auger ${s.relays.auger ? 'is-on' : ''}`}>
      <rect className="lr-line" x="62" y="282" width="80" height="20" rx="6" />
      <path className="lr-line lr-thin lr-flights" d="M70 298 l 8 -12 M84 298 l 8 -12 M98 298 l 8 -12 M112 298 l 8 -12 M126 298 l 8 -12" />
    </g>
    <path className="lr-line" d="M70 252 V 282" />
    <text className="lr-label" x="70" y="200" textAnchor="middle">{tr('ov.feed')}</text>
    {!s.live && <g className="lr-nolink" role="status"><rect x="150" y="196" width="170" height="48" rx="10" /><text x="235" y="227" textAnchor="middle">{tr('ov.noLink')}</text></g>}
  </svg>
}
