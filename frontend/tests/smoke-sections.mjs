// Smoke check: open every dashboard section in headless Chrome against a running
// dashboard (python main.py dashboard) and report JS errors, failed API calls,
// and whether the Science page shows real data and figures.
//
// Usage:  node tests/smoke-sections.mjs            (default http://127.0.0.1:8765)
//         set BIOREACTOR_URL=http://127.0.0.1:9000 && node tests/smoke-sections.mjs
import { chromium } from 'playwright-core'

const baseUrl = process.env.BIOREACTOR_URL ?? 'http://127.0.0.1:8765'
const chromePath = process.env.CHROME_PATH ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const sections = ['overview', 'substrates', 'chat', 'reactor', 'market', 'science', 'system', 'demo']

const browser = await chromium.launch({ executablePath: chromePath, headless: true })
const page = await browser.newPage({ viewport: { width: 1366, height: 768 } })

let currentSection = 'start'
const problems = []
page.on('pageerror', error => problems.push(`[${currentSection}] JS error: ${error.message}`))
page.on('response', response => {
  const isApi = response.url().includes('/api/') || response.url().includes('/dashboard-api/')
  if (isApi && response.status() >= 500) {
    problems.push(`[${currentSection}] HTTP ${response.status()} ${response.url()}`)
  }
})

const results = []
for (const section of sections) {
  currentSection = section
  await page.goto(`${baseUrl}/dashboard/#/${section}`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(800)
  const text = await page.locator('main').innerText().catch(() => '')
  const brokenImages = await page.evaluate(
    () => [...document.images].filter(image => image.complete && image.naturalWidth === 0).map(image => image.src),
  )
  for (const src of brokenImages) problems.push(`[${section}] broken image: ${src}`)
  results.push({ section, url: page.url(), textLength: text.length, images: await page.locator('main img').count() })
}

// The Science page must show real data from reports/ and models/.
currentSection = 'science'
await page.goto(`${baseUrl}/dashboard/#/science`, { waitUntil: 'networkidle' })
await page.waitForTimeout(800)
const scienceImages = await page.locator('main img').count()
const scienceText = await page.locator('main').innerText()
const scienceHasNumbers = /\d+[.,]\d+/.test(scienceText)

await browser.close()

console.table(results)
console.log(`Science: images=${scienceImages}, has numeric metrics=${scienceHasNumbers}`)
if (!scienceHasNumbers || scienceImages === 0) problems.push('[science] no data or figures shown')
if (problems.length) {
  console.log('PROBLEMS:\n' + problems.join('\n'))
  process.exit(1)
}
console.log('OK: all sections opened without errors')
