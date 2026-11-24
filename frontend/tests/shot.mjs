// Quick screenshot of one section while working:  node tests/shot.mjs <section> [lang] [width] [height] [out.png] [scientific]
import { chromium } from 'playwright-core'
const [section = 'overview', lang = 'ru', width = '1366', height = '768', out = `reports/shot-${section}.png`, scientific] = process.argv.slice(2)
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true })
const context = await browser.newContext({ viewport: { width: Number(width), height: Number(height) } })
await context.addInitScript(([l, s]) => { try { localStorage.setItem('bioreactor.language', l); localStorage.setItem('bioreactor-display-mode', s ? 'scientific' : 'simple') } catch {} }, [lang, scientific === 'scientific'])
const page = await context.newPage()
const errors = []
page.on('pageerror', e => errors.push(e.message))
await page.goto(`${process.env.BASE_URL ?? 'http://127.0.0.1:8766'}/dashboard/#/${section}`)
await page.waitForTimeout(2500)
await page.screenshot({ path: out, fullPage: true })
console.log(out, errors.length ? 'ERRORS: ' + errors.join(' | ') : 'no errors')
await browser.close()
