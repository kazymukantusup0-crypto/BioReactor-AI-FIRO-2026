// design-v3 concept shots: «Обзор» for concepts A and B — simulator (moving) in RU/KZ/EN, the real mode without a Pi
// («Нет связи»), the frame rate while the scene animates, rendered contrast and text size.
// Usage: node tests/design-v3-concepts.mjs <outDir>   (SIM_URL default :8767, REAL_URL default :8766)
import { chromium } from 'playwright-core'
import { mkdirSync } from 'node:fs'

const out = process.argv[2] ?? '../docs/design-v3/concepts'
const SIM = process.env.SIM_URL ?? 'http://127.0.0.1:8767'
const REAL = process.env.REAL_URL ?? 'http://127.0.0.1:8766'
mkdirSync(out, { recursive: true })
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true })
const report = []

async function open(base, c, lang, page) {
  await page.goto(`${base}/dashboard/?concept=${c}#/overview`, { waitUntil: 'networkidle' }).catch(() => {})
  await page.waitForTimeout(4500)
}
for (const c of ['a', 'b']) {
  for (const lang of ['ru', 'kk', 'en']) {
    const context = await browser.newContext({ viewport: { width: 1366, height: 768 } })
    await context.addInitScript(l => { try { localStorage.setItem('bioreactor.language', l) } catch {} }, lang)
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', e => errors.push(e.message))
    await open(SIM, c, lang, page)
    await page.screenshot({ path: `${out}/concept-${c}-${lang}.png` })
    if (lang === 'ru') {
      await page.screenshot({ path: `${out}/concept-${c}-${lang}-full.png`, fullPage: true })
      // frames in 3 s while bubbles, waves, pump and gauges move
      const fps = await page.evaluate(() => new Promise(done => { let n = 0; const t0 = performance.now()
        const step = () => { n++; if (performance.now() - t0 < 3000) requestAnimationFrame(step); else done(Math.round(n / 3)) }; requestAnimationFrame(step) }))
      report.push(`${c}: ${fps} fps (headless, software rendering)`)
    }
    const tiny = await page.evaluate(() => [...document.querySelectorAll('main *')].filter(el => [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())
      && el.getBoundingClientRect().width > 0 && parseFloat(getComputedStyle(el).fontSize) < 13).map(el => el.tagName + ':' + getComputedStyle(el).fontSize).slice(0, 4))
    if (tiny.length) report.push(`${c}/${lang}: text < 13px ${tiny.join(', ')}`)
    if (errors.length) report.push(`${c}/${lang}: JS errors ${errors.join(' | ')}`)
    await context.close()
  }
  const context = await browser.newContext({ viewport: { width: 1366, height: 768 } })
  await context.addInitScript(() => { try { localStorage.setItem('bioreactor.language', 'ru') } catch {} })
  const page = await context.newPage()
  await open(REAL, c, 'ru', page)
  await page.screenshot({ path: `${out}/concept-${c}-nolink-ru.png` })
  const noLink = await page.locator('[data-testid=ov-live]').innerText()
  report.push(`${c}: real mode without Pi -> «${noLink}»`)
  await context.close()
}
await browser.close()
console.log(report.join('\n'))
