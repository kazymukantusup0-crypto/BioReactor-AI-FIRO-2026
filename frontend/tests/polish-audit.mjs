// Screenshots for the dashboard polish (before / after) and a list of what is on each screen.
//   python main.py dashboard --port 8766 --no-browser --no-scheduler
//   node tests/polish-audit.mjs before        (or: after)   — BASE_URL, CHROME_PATH optional
// Output: reports/polish/<stage>/ (PNG + audit.json with font sizes, colours, overflow, Cyrillic in EN).
import { chromium } from 'playwright-core'
import { mkdirSync, writeFileSync } from 'node:fs'

const stage = process.argv[2] ?? 'before'
const base = process.env.BASE_URL ?? 'http://127.0.0.1:8766'
const out = `reports/polish/${stage}`
mkdirSync(out, { recursive: true })
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true, args: ['--no-first-run', '--disable-background-networking'] })
const SECTIONS = ['overview', 'substrates', 'chat', 'reactor', 'market', 'science', 'system', 'demo']
const LANGS = { ru: 'RU', kk: 'ҚАЗ', en: 'EN' }
const VIEWPORTS = { '1366': { width: 1366, height: 768 }, '1920': { width: 1920, height: 1080 }, 'projector': { width: 1280, height: 720 } }
const audit = { stage, sections: {}, substrates: {}, errors: [] }

async function open(viewport, lang, jury = false) {
  const context = await browser.newContext({ viewport })
  await context.addInitScript(([l, j]) => { try { localStorage.setItem('bioreactor-language', l); localStorage.setItem('bioreactor-agent-v10-jury', j ? '1' : '0') } catch {} }, [lang, jury])
  const page = await context.newPage()
  page.on('pageerror', error => audit.errors.push(`${lang} ${viewport.width}: ${error.message}`))
  page.on('response', r => { if (r.url().includes('/api/') && r.status() >= 400) audit.errors.push(`${lang} HTTP ${r.status()} ${r.url()}`) })
  await page.goto(`${base}/dashboard/#/overview`)
  await page.locator('.language-switch').waitFor()
  await page.locator('.language-switch').getByRole('radio', { name: LANGS[lang] }).click()
  return { context, page }
}

// What a screen looks like: font sizes in use, small text, colours, horizontal overflow, buttons.
const measure = page => page.evaluate(() => {
  const main = document.querySelector('main') ?? document.body
  const sizes = {}, colors = {}, backgrounds = {}, radii = {}
  let small = 0, smallExamples = []
  for (const el of main.querySelectorAll('*')) {
    const style = getComputedStyle(el)
    if (style.display === 'none' || style.visibility === 'hidden') continue
    const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())
    if (own) {
      const size = Math.round(parseFloat(style.fontSize))
      sizes[size] = (sizes[size] ?? 0) + 1
      colors[style.color] = (colors[style.color] ?? 0) + 1
      if (size < 13) { small++; if (smallExamples.length < 6) smallExamples.push(`${size}px: ${el.textContent.trim().slice(0, 40)}`) }
    }
    if (style.backgroundColor !== 'rgba(0, 0, 0, 0)') backgrounds[style.backgroundColor] = (backgrounds[style.backgroundColor] ?? 0) + 1
    if (style.borderRadius !== '0px') radii[style.borderRadius] = (radii[style.borderRadius] ?? 0) + 1
  }
  return {
    height: document.documentElement.scrollHeight,
    horizontalScroll: document.documentElement.scrollWidth > window.innerWidth + 1,
    fontSizes: sizes, smallTextCount: small, smallExamples,
    textColors: Object.keys(colors).length, backgrounds: Object.keys(backgrounds).length, radii: Object.keys(radii),
    buttons: [...main.querySelectorAll('button')].filter(b => b.offsetParent).length,
    text: main.innerText.slice(0, 4000),
  }
})

// 1) All sections, 3 languages, 3 screen sizes (projector = 1280x720 with jury mode on).
for (const lang of Object.keys(LANGS)) {
  for (const [vp, viewport] of Object.entries(VIEWPORTS)) {
    const { context, page } = await open(viewport, lang, vp === 'projector')
    for (const section of SECTIONS) {
      await page.evaluate(id => { window.location.hash = '/' + id }, section)
      await page.waitForTimeout(1800)
      await page.screenshot({ path: `${out}/${lang}-${vp}-${section}.png`, fullPage: vp !== 'projector' })
      if (vp === '1366') {
        const m = await measure(page)
        if (lang === 'en') m.cyrillic = [...new Set(m.text.match(/[А-Яа-яЁёӘәҒғҚқҢңӨөҰұҮүҺһІі][^\n]{0,40}/g) ?? [])].slice(0, 15)
        if (lang === 'kk') m.russianOnly = [...new Set(m.text.match(/[^\n]{0,20}[ЫыЭэЪъ][^\n]{0,20}/g) ?? [])].slice(0, 15)
        delete m.text
        audit.sections[`${lang}-${section}`] = m
      }
    }
    await context.close()
  }
}

// 2) «Сырьё и смеси»: the farmer's scenarios, RU / ҚАЗ / EN.
const resultText = page => page.locator('main').innerText()
const step = async (page, lang, name, action) => {
  try { await action() } catch (error) { audit.substrates[`${lang}-${name}`] = { error: String(error).slice(0, 300) }; return }
  await page.waitForTimeout(2600)  // the page recalculates 0.7 s after the last change
  await page.screenshot({ path: `${out}/${lang}-substrates-${name}.png`, fullPage: true })
  const text = await resultText(page)
  audit.substrates[`${lang}-${name}`] = {
    numbers: (text.match(/[≈~]?\s?\d+[.,]?\d*\s?[–-]\s?\d+[.,]?\d*\s?(м³|m³|кВт·ч|kWh|л|L)/g) ?? []).slice(0, 12),
    notices: await page.locator('.notice, [role=status], [role=alert]').allInnerTexts().then(v => v.map(s => s.slice(0, 160)).slice(0, 6)),
    height: await page.evaluate(() => document.documentElement.scrollHeight),
  }
}
for (const lang of Object.keys(LANGS)) {
  const { context, page } = await open({ width: 1366, height: 768 }, lang)
  await page.evaluate(() => { localStorage.removeItem('bioreactor-inventory-v8.1'); localStorage.removeItem('bioreactor-calculator-draft-v9') })
  await page.evaluate(() => { window.location.hash = '/substrates' })
  await page.waitForTimeout(500); await page.reload(); await page.locator('[data-testid="material-0"]').waitFor()
  const qty = page.locator('[data-testid="quantity-0"]')
  await step(page, lang, '1-single-default', async () => {})
  await step(page, lang, '2-single-200L', async () => {
    await page.locator('select[aria-label]').nth(2).selectOption('L').catch(() => {})
    await qty.fill('200')
  })
  await step(page, lang, '3-unit-kg-to-t', async () => { await page.locator('[data-testid="quantity-0"]').locator('xpath=ancestor::div[1]').locator('select').last().selectOption('t') })
  await step(page, lang, '4-empty-quantity', async () => { await qty.fill('') })
  await step(page, lang, '5-negative', async () => { await qty.fill('-5') })
  await step(page, lang, '6-huge', async () => { await qty.fill('1e12') })
  await step(page, lang, '7-unknown-other-organic', async () => { await qty.fill('30'); await page.locator('[data-testid="material-0"]').selectOption('food_waste') })
  // Mixture: in the simple view there is no «add component» button — switch to the scientific view.
  await step(page, lang, '8-mixture-3', async () => {
    const simpleAdd = await page.getByRole('button').filter({ has: page.locator('svg.lucide-plus') }).count()
    audit.substrates[`${lang}-add-button-in-simple-view`] = simpleAdd
    await page.locator('.page-heading .display-mode button').nth(1).click()
    await page.locator('[data-testid="material-0"]').selectOption('cattle_manure')
    await qty.fill('100')
    const add = page.getByRole('button').filter({ has: page.locator('svg.lucide-plus') })
    await add.click(); await add.click()
    await page.locator('[data-testid="material-2"]').selectOption('straw')
  })
  await context.close()
}

writeFileSync(`${out}/audit.json`, JSON.stringify(audit, null, 1))
console.log(`screens: ${out}, errors: ${audit.errors.length}`)
for (const e of audit.errors.slice(0, 20)) console.log('  ' + e)
await browser.close()
