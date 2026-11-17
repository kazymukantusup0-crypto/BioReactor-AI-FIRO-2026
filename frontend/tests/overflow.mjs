// Which elements stick out of a narrow screen:  node tests/overflow.mjs <section> [width] [lang]
import { chromium } from 'playwright-core'
const [section = 'chat', width = '390', lang = 'en'] = process.argv.slice(2)
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true })
const context = await browser.newContext({ viewport: { width: Number(width), height: 844 } })
await context.addInitScript(l => { try { localStorage.setItem('bioreactor.language', l) } catch {} }, lang)
const page = await context.newPage()
await page.goto(`${process.env.BASE_URL ?? 'http://127.0.0.1:8766'}/dashboard/#/${section}`)
await page.waitForTimeout(2000)
const result = await page.evaluate(() => {
  const limit = window.innerWidth
  const out = []
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect()
    if (r.right > limit + 1 && r.width > 0 && getComputedStyle(el).position !== 'fixed') out.push(`${el.tagName.toLowerCase()}.${[...el.classList].join('.')} right=${Math.round(r.right)} w=${Math.round(r.width)}`)
  }
  return { scrollWidth: document.documentElement.scrollWidth, limit, out: out.slice(0, 15) }
})
console.log(JSON.stringify(result, null, 1))
await browser.close()
