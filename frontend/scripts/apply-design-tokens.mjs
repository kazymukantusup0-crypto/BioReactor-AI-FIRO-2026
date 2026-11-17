// One-time move of the older CSS onto the design system tokens (src/design.css). Run again: it is idempotent.
//   node scripts/apply-design-tokens.mjs            -> rewrites src/*.css (not design.css), prints what changed
// Rules (simple on purpose, written down in docs/progress.md):
//   font-size N px  -> 8-step scale, smallest 13 px:  <=10.5 xs(13) · <=12.5 sm(14) · <=14 md(15) · <=17 lg(17)
//                      <=21 xl(20) · <=26 2xl(24) · <=33 3xl(30) · else hero(40)
//   color #hex      -> very dark (L < 25 %): on-accent (text on a bright button); grey-ish: by lightness text-strong / text / text-muted / text-faint; coloured: by hue accent /
//                      warn / danger / info. 8-digit (#rrggbbaa) colours are left as they are.
//   background #hex -> dark grey-ish: bg / surface-1 / surface-2 / surface-3; dark green: accent-soft
//   border colour   -> grey-ish: border / border-strong
//   border-radius   -> <=6 sm · <=11 md · <100 lg · else pill (50% stays)
import fs from 'node:fs'
import path from 'node:path'

const dir = path.resolve('src')
const files = fs.readdirSync(dir).filter(f => f.endsWith('.css') && f !== 'design.css')

function hsl(hex) {
  let h = hex.slice(1)
  if (h.length === 3) h = [...h].map(c => c + c).join('')
  const [r, g, b] = [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16) / 255)
  const max = Math.max(r, g, b), min = Math.min(r, g, b), l = (max + min) / 2, d = max - min
  const s = d === 0 ? 0 : d / (1 - Math.abs(2 * l - 1))
  let hue = 0
  if (d) hue = max === r ? 60 * (((g - b) / d) % 6) : max === g ? 60 * ((b - r) / d + 2) : 60 * ((r - g) / d + 4)
  return { h: (hue + 360) % 360, s, l }
}
const fontSize = px => px <= 10.5 ? 'xs' : px <= 12.5 ? 'sm' : px <= 14 ? 'md' : px <= 17 ? 'lg' : px <= 21 ? 'xl' : px <= 26 ? '2xl' : px <= 33 ? '3xl' : 'hero'
function textColor(hex) {
  const { h, s, l } = hsl(hex)
  if (l < .25) return 'on-accent'  // dark text on a bright (accent) button
  if (s < .42 || l > .82) return l >= .86 ? 'text-strong' : l >= .7 ? 'text' : l >= .55 ? 'text-muted' : 'text-faint'
  if (h >= 130 && h < 190) return 'accent'
  if (h >= 25 && h < 70) return 'warn'
  if (h < 20 || h >= 330) return 'danger'
  if (h >= 190 && h < 260) return 'info'
  return null
}
function background(hex) {
  const { h, s, l } = hsl(hex)
  if (l > .2) return null
  if (s < .45) return l < .065 ? 'bg' : l < .1 ? 'surface-1' : l < .135 ? 'surface-2' : 'surface-3'
  if (h >= 130 && h < 190) return 'accent-soft'
  return null
}
function border(hex) {
  const { s, l } = hsl(hex)
  if (s >= .45 || l > .4) return null
  return l < .22 ? 'border' : 'border-strong'
}
const radius = px => px <= 6 ? 'sm' : px <= 11 ? '' : px < 100 ? 'lg' : 'pill'

const counts = {}
const bump = key => { counts[key] = (counts[key] ?? 0) + 1 }
for (const file of files) {
  const full = path.join(dir, file)
  let css = fs.readFileSync(full, 'utf8')
  css = css.replace(/font-size:\s*(\d+(?:\.\d+)?)px(\s*!important)?/g, (all, px, imp) => { bump('font-size'); return `font-size:var(--fs-${fontSize(Number(px))})${imp ?? ''}` })
  css = css.replace(/(^|[;{\s])color:\s*(#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3})(?![0-9a-fA-F])/g, (all, pre, hex) => {
    const token = textColor(hex); if (!token) return all
    bump('color'); return `${pre}color:var(--${token})`
  })
  css = css.replace(/(^|[;{\s])background(-color)?:\s*(#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3})(?![0-9a-fA-F])/g, (all, pre, suffix, hex) => {
    const token = background(hex); if (!token) return all
    bump('background'); return `${pre}background${suffix ?? ''}:var(--${token})`
  })
  css = css.replace(/(border(?:-top|-bottom|-left|-right)?(?:-color)?:[^;}]*?)(#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3})(?![0-9a-fA-F])/g, (all, pre, hex) => {
    const token = border(hex); if (!token) return all
    bump('border'); return `${pre}var(--${token})`
  })
  css = css.replace(/border-radius:\s*(\d+(?:\.\d+)?)px(?=\s*[;}!])/g, (all, px) => { bump('radius'); const r = radius(Number(px)); return `border-radius:var(--radius${r ? '-' + r : ''})` })
  fs.writeFileSync(full, css)
}
console.log('changed declarations:', counts)
