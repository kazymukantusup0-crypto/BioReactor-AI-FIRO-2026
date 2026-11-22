// design-v2: replace hard-coded colours in src/*.css with design tokens (design.css :root).
// Decorative gradients become flat surfaces; mint shades become the accent; translucent tints become
// color-mix() of the meaning tokens. Prints anything left over. Run once:  node scripts/tokenize-colors.mjs [--check]
import { readFileSync, writeFileSync, readdirSync } from 'node:fs'

const whole = [ // exact expressions first (gradients, shadows)
  ['linear-gradient(140deg,#13252a,#101c22)', 'var(--surface-1)'],
  ['linear-gradient(135deg,#123128,#0f1f22)', 'var(--accent-wash)'],
  ['linear-gradient(110deg,#21433455,#12252b)', 'var(--accent-wash)'],
  ['linear-gradient(100deg,#1a3d32,#152b29)', 'var(--accent-wash)'],
  ['linear-gradient(110deg,#183129,#142422)', 'var(--accent-wash)'],
  ['linear-gradient(130deg,#121e25,#101b22)', 'var(--surface-1)'],
  ['radial-gradient(ellipse at 80% 45%,#1f4a3a44,transparent 75%),linear-gradient(100deg,#132228,#101f25)', 'var(--surface-1)'],
  ['linear-gradient(130deg,#142923,#111d24)', 'var(--accent-wash)'],
  ['linear-gradient(135deg,#234936,#16322a)', 'var(--accent-soft)'],
  ['radial-gradient(ellipse at 0 50%,#255c3e33,transparent 70%),#122029', 'var(--surface-1)'],
  ['linear-gradient(110deg,#17352b99,#152a2b88)', 'var(--accent-wash)'],
  ['box-shadow:0 0 50px #3e98701a', 'box-shadow:none'],
  ['box-shadow:0 6px 20px #00000008', 'box-shadow:none'],
  ['box-shadow: 0 20px 60px rgba(0, 0, 0, .5)', 'box-shadow: var(--shadow-lg)'],
  ['rgba(60, 8, 8, .94)', 'var(--alarm-bg)'],
  ['rgba(110, 14, 14, .96)', 'var(--alarm-bg-strong)'],
  ['rgba(3, 8, 10, .72)', 'var(--scrim)'],
  ['background:#fff}.scientific-figure img', 'background:var(--figure-bg)}.scientific-figure img'],
]
const groups = {
  'var(--accent)': '55d6af 60d6ad 64d5ae 62d2aa 63d5af 5dd0a6 5bd2a9 64cfaa 61d6ad 65dcb9 70e1c2 68ddba 4fbba0',
  'var(--accent-strong)': '81e4c0 8aebcd',
  'var(--accent-line)': '4c9479 58a48a 4f9b83 5c9a80 5eaa8c 64b892 65bba5',
  'var(--accent-soft-strong)': '1d4d40 235c4c 2f7562 32644e 254b3c 224b35 274239',
  'var(--accent-tint)': '16362c55 17382a66 214c3233 1e403333 19352d66 17312b55 64d5ae0a',
  'var(--accent-ring)': '55d6af33',
  'var(--info)': '77c5d2',
  'var(--info-tint)': '1c45452b 16363b66',
  'var(--warn)': 'd6ad67 ddbb80 d4b471',
  'var(--warn-line)': '6b5527',
  'var(--warn-tint)': '493b1922 43362255 44371e30 3f362320 3d352333 24241d44',
  'var(--danger)': 'e07a7a',
  'var(--danger-line)': '7a3a33',
  'var(--danger-tint)': '482e3255 452b3333',
  'var(--surface-3)': '2c3c44',
  'var(--surface-2)': '1c2c332e',
  'var(--surface-1)': '0d1c23',
  'var(--border-strong)': '526470',
  'var(--overlay)': '0d161ce8',
  'var(--bg)': '0b161d',
  'var(--bg-ring)': '0e1b2333',
  'var(--scrim)': '0009',
  // E-STOP and the full-screen alarm: their own tokens (red stays red in every theme)
  'var(--estop)': 'b3261e', 'var(--estop-hover)': 'd0342a', 'var(--estop-edge)': 'ffb3a8', 'var(--estop-shadow)': '6e1010',
  'var(--on-estop-muted)': 'ffe1dc', 'var(--on-alarm-muted)': 'ffe9e6', 'var(--alarm-ink)': '5a0d0d',
}
const map = new Map(Object.entries(groups).flatMap(([token, list]) => list.split(' ').map(hex => [hex, token])))
const check = process.argv.includes('--check')
let left = 0
for (const file of readdirSync('src').filter(f => f.endsWith('.css'))) {
  const path = `src/${file}`
  const text = readFileSync(path, 'utf8')
  // design.css: leave the :root token block alone
  const start = file === 'design.css' ? text.indexOf('}', text.indexOf(':root')) + 1 : 0
  let head = text.slice(0, start), body = text.slice(start)
  for (const [from, to] of whole) body = body.split(from).join(to)
  body = body.replace(/#([0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})\b/g, (m, hex) => {
    const key = hex.toLowerCase()
    if (map.has(key)) return map.get(key)
    if (file === 'reactor.css' && (key === 'fff')) return 'var(--on-alarm)'
    return m
  })
  // the Tailwind theme block in styles.css mirrors the tokens
  body = body.replace('--color-background: #0b1217', '--color-background: var(--bg)').replace('--color-panel: #111c22', '--color-panel: var(--surface-1)').replace('--color-accent: #55d6af', '--color-accent: var(--accent)')
  const rest = [...body.matchAll(/#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)/g)].map(m => m[0])
  left += rest.length
  if (rest.length) console.log(`${path}: left ${rest.join(' ')}`)
  if (!check && head + body !== text) writeFileSync(path, head + body)
}
console.log(left ? `${left} literal colours left outside :root` : 'no literal colours outside :root')
