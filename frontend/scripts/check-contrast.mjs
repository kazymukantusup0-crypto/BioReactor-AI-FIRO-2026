// Contrast of the design system text colours on the surfaces (WCAG 2): node scripts/check-contrast.mjs
// Every text token must be >= 4.5:1 on --surface-1 and --surface-2 (cards), so it still reads on a projector.
import fs from 'node:fs'

const css = fs.readFileSync(new URL('../src/design.css', import.meta.url), 'utf8')
const token = name => css.match(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`))?.[1]
const lum = hex => {
  const [r, g, b] = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255).map(c => c <= .03928 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4)
  return .2126 * r + .7152 * g + .0722 * b
}
const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + .05) / (y + .05) }
let bad = 0
for (const surface of ['bg', 'surface-1', 'surface-2', 'surface-3']) {
  for (const text of ['text-strong', 'text', 'text-muted', 'text-faint', 'accent', 'warn', 'danger', 'info']) {
    const value = ratio(token(text), token(surface))
    const ok = value >= 4.5
    if (!ok) bad++
    console.log(`${ok ? 'OK ' : 'LOW'} ${text.padEnd(12)} on ${surface.padEnd(10)} ${value.toFixed(2)}:1`)
  }
}
console.log(`on-accent on accent ${ratio(token('on-accent'), token('accent')).toFixed(2)}:1`)
process.exit(bad ? 1 : 0)
