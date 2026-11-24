// Rendered contrast scan: every visible text element vs. its effective background,
// with element opacity taken into account. Reports pairs under 4.5:1 (3:1 for ≥24px or ≥18.66px bold).
// Usage: node tests/contrast-scan.mjs [sections=overview,chat,reactor,substrates,market,science,system,demo] [lang=ru]
import { chromium } from 'playwright-core'
const [sectionArg = 'overview,chat,reactor,substrates,market,science,system,demo', lang = 'ru'] = process.argv.slice(2)
const base = process.env.BASE_URL ?? 'http://127.0.0.1:8766'
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true })
const context = await browser.newContext({ viewport: { width: 1366, height: 768 }, reducedMotion: 'reduce' })
await context.addInitScript(l => { try { localStorage.setItem('bioreactor.language', l) } catch {} }, lang)
const page = await context.newPage()
let failures = 0
for (const section of sectionArg.split(',')) {
  await page.goto(`${base}/dashboard/#/${section}`, { waitUntil: 'networkidle' }).catch(() => {})
  await page.waitForTimeout(1500)
  const bad = await page.evaluate(() => {
    const parse = c => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); return { r: p[0], g: p[1], b: p[2], a: p[3] ?? 1 } }
    const lum = ({ r, g, b }) => { const f = v => { v /= 255; return v <= .03928 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4 }; return .2126 * f(r) + .7152 * f(g) + .0722 * f(b) }
    const mix = (top, bot, a) => ({ r: top.r * a + bot.r * (1 - a), g: top.g * a + bot.g * (1 - a), b: top.b * a + bot.b * (1 - a) })
    const bgOf = el => { // composite backgrounds from the root down
      const chain = []; for (let e = el; e; e = e.parentElement) chain.push(e)
      let bg = parse(getComputedStyle(document.body).backgroundColor) || { r: 11, g: 18, b: 23, a: 1 }
      if (bg.a < 1) bg = { r: 11, g: 18, b: 23, a: 1 }
      for (const e of chain.reverse()) { const c = parse(getComputedStyle(e).backgroundColor); if (c && c.a > 0) bg = mix(c, bg, c.a) }
      return bg
    }
    const opacityOf = el => { let o = 1; for (let e = el; e; e = e.parentElement) o *= Number(getComputedStyle(e).opacity); return o }
    const out = []
    for (const el of document.querySelectorAll('body *')) {
      if (![...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) continue
      const s = getComputedStyle(el); const r = el.getBoundingClientRect()
      if (!r.width || !r.height || s.visibility === 'hidden' || el.closest('.skip-link, [aria-hidden="true"], .sr-only')) continue
      const bg = bgOf(el); const fg0 = parse(s.color); if (!fg0) continue
      const fg = mix(fg0, bg, fg0.a * opacityOf(el))
      const L1 = lum(fg), L2 = lum(bg); const ratio = (Math.max(L1, L2) + .05) / (Math.min(L1, L2) + .05)
      const size = parseFloat(s.fontSize), bold = Number(s.fontWeight) >= 700
      const need = size >= 24 || (bold && size >= 18.66) ? 3 : 4.5
      if (ratio < need) out.push(`${ratio.toFixed(2)}:1 (need ${need}) ${el.tagName.toLowerCase()}.${String(el.className).split(' ')[0]} "${el.textContent.trim().slice(0, 40)}"${el.disabled || el.closest('[disabled]') ? ' [disabled]' : ''}`)
    }
    return [...new Set(out)]
  })
  failures += bad.length
  console.log(`== ${section}: ${bad.length ? bad.length + ' low-contrast' : 'ok'}`)
  for (const b of bad.slice(0, 12)) console.log('   ' + b)
}
await browser.close()
console.log(failures ? `TOTAL ${failures}` : 'all text ≥ 4.5:1')
