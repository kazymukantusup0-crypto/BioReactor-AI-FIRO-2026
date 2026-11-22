// Design screenshots: every section × language at projector size (1366×768 viewport, full page).
// Usage: node tests/design-shots.mjs <outDir> [langs=ru,kk,en] [sections=...]
// Needs a running dashboard (BASE_URL, default http://127.0.0.1:8766).
import { chromium } from 'playwright-core'
import { mkdirSync } from 'node:fs'

const [outDir = '../docs/design-v2/shots', langArg = 'ru,kk,en', sectionArg = 'overview,chat,reactor,substrates,market,science,system,demo'] = process.argv.slice(2)
const base = process.env.BASE_URL ?? 'http://127.0.0.1:8766'
mkdirSync(outDir, { recursive: true })
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true })
const problems = []
for (const lang of langArg.split(',')) {
  const context = await browser.newContext({ viewport: { width: 1366, height: 768 }, reducedMotion: 'reduce' })
  await context.addInitScript(l => { try { localStorage.setItem('bioreactor.language', l) } catch {} }, lang)
  const page = await context.newPage()
  page.on('pageerror', e => problems.push(`[${lang}] ${e.message}`))
  for (const section of sectionArg.split(',')) {
    await page.goto(`${base}/dashboard/#/${section}`, { waitUntil: 'networkidle' }).catch(() => {})
    await page.waitForTimeout(1800)
    const file = `${outDir}/${section}-${lang}.png`
    await page.screenshot({ path: file, fullPage: true })
    // small text check: any visible text node rendered under 13 px
    const tiny = await page.evaluate(() => [...document.querySelectorAll('body *')].filter(el => {
      if (!el.childNodes.length || ![...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) return false
      const s = getComputedStyle(el); const r = el.getBoundingClientRect()
      return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && parseFloat(s.fontSize) < 13
    }).slice(0, 5).map(el => `${el.tagName.toLowerCase()}.${el.className}:${getComputedStyle(el).fontSize}`))
    if (tiny.length) problems.push(`[${lang}/${section}] text < 13px: ${tiny.join(', ')}`)
    console.log(file)
  }
  await context.close()
}
await browser.close()
console.log(problems.length ? 'PROBLEMS:\n' + problems.join('\n') : 'no problems')
