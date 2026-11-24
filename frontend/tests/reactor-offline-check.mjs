// «Реактор» without the real Pi, RU / ҚАЗ / EN, no page reload:
//   simulator (data, live buttons) -> «network cut» (grey «Нет связи») -> back (live buttons again)
//   real mode without a Pi: grey «Нет связи», E-STOP grey.
// The confirmation dialog is only opened and closed with «Cancel»: no relay is switched.
// Usage: node tests/reactor-offline-check.mjs <outDir>   (SIM_URL default :8767 simulator, REAL_URL default :8766)
import { chromium } from 'playwright-core'
import { mkdirSync } from 'node:fs'

const out = process.argv[2] ?? '../docs/design-v2/after/offline'
const SIM = process.env.SIM_URL ?? 'http://127.0.0.1:8767'
const REAL = process.env.REAL_URL ?? 'http://127.0.0.1:8766'
const NO_LINK = { ru: 'Нет связи', kk: 'Байланыс жоқ', en: 'No link' }
mkdirSync(out, { recursive: true })
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true })
const failures = []
const check = (ok, text) => { console.log(`${ok ? 'OK ' : 'BAD'} ${text}`); if (!ok) failures.push(text) }
const RELAYS = ['heat', 'cool', 'pump', 'auger']

async function buttons(page) {
  return page.evaluate(relays => relays.map(r => {
    const b = document.querySelector(`[data-testid=rx-relay-button-${r}]`)
    return b && { relay: r, disabled: b.disabled, offline: b.classList.contains('rx-offline-button'), text: b.textContent.trim() }
  }), RELAYS)
}

for (const lang of ['ru', 'kk', 'en']) {
  const context = await browser.newContext({ viewport: { width: 1366, height: 768 } })
  await context.addInitScript(l => { try { localStorage.setItem('bioreactor.language', l) } catch {} }, lang)
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', e => errors.push(e.message))

  // 1. simulator: data and live buttons
  await page.goto(`${SIM}/dashboard/#/reactor`, { waitUntil: 'networkidle' })
  await page.waitForFunction(() => !document.querySelector('[data-testid=rx-relay-button-heat]')?.classList.contains('rx-offline-button'), null, { timeout: 15000 }).catch(() => {})
  await page.waitForTimeout(1500)
  const values = await page.$$eval('.rx-reading-value', els => els.map(e => e.textContent.trim()))
  check(values.length === 4 && values.every(v => /\d/.test(v)), `[${lang}] simulator: 4 readings with numbers (${values.join(' | ')})`)
  const levels = await page.$$eval('.rx-level', els => els.map(e => e.className.replace('rx-level ', '') + ':' + e.textContent.trim()))
  check(levels.length >= 4 && levels.every(l => !l.startsWith('rx-level-unknown')), `[${lang}] simulator: every reading has a status (${levels.join(' | ')})`)
  let b = await buttons(page)
  const live = b.filter(x => x && !x.offline)
  check(live.length === 4, `[${lang}] simulator: relay buttons are live (${b.map(x => `${x.relay}:${x.disabled ? 'disabled' : 'enabled'}`).join(', ')})`)
  // a button that is enabled opens the dialog; «Cancel» closes it (nothing is switched)
  const enabled = b.find(x => x && !x.disabled)
  if (enabled) {
    await page.locator(`[data-testid=rx-relay-button-${enabled.relay}]`).click()
    const dialog = page.locator('.rx-modal')
    check(await dialog.isVisible(), `[${lang}] confirmation dialog opens (${enabled.relay})`)
    await page.screenshot({ path: `${out}/reactor-sim-confirm-${lang}.png` })
    await page.locator('.rx-modal button').filter({ hasNotText: /Да|Иә|Yes/ }).first().click()
    await page.waitForTimeout(400)
    check(!(await dialog.isVisible().catch(() => false)), `[${lang}] «Cancel» closes the dialog`)
  }
  await page.screenshot({ path: `${out}/reactor-sim-${lang}.png` })

  // 2. same page, network cut -> grey «Нет связи»
  await page.locator('[data-testid=rx-sim-network]').scrollIntoViewIfNeeded()
  await page.locator('[data-testid=rx-sim-network]').click()
  await page.waitForFunction(() => document.querySelector('[data-testid=rx-relay-button-heat]')?.classList.contains('rx-offline-button'), null, { timeout: 15000 }).catch(() => {})
  b = await buttons(page)
  check(b.every(x => x && x.disabled && x.offline && x.text === NO_LINK[lang]), `[${lang}] network cut: every relay button grey «${NO_LINK[lang]}»`)
  check(await page.locator('[data-testid=rx-estop]').isDisabled(), `[${lang}] network cut: E-STOP disabled (grey)`)
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: `${out}/reactor-sim-cut-${lang}.png` })

  // 3. same page, network back -> live again without reload
  await page.locator('[data-testid=rx-sim-network]').click()
  await page.waitForFunction(() => !document.querySelector('[data-testid=rx-relay-button-heat]')?.classList.contains('rx-offline-button'), null, { timeout: 15000 }).catch(() => {})
  b = await buttons(page)
  check(b.every(x => x && !x.offline), `[${lang}] network back: buttons live again, no reload`)
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: `${out}/reactor-sim-back-${lang}.png` })

  // 4. real mode, no Pi on the network
  await page.goto(`${REAL}/dashboard/#/reactor`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(3000)
  b = await buttons(page)
  check(b.every(x => x && x.disabled && x.offline && x.text === NO_LINK[lang]), `[${lang}] real mode without Pi: grey «${NO_LINK[lang]}»`)
  const empty = await page.$$eval('.rx-reading-value', els => els.filter(e => !e.textContent.trim()).length)
  check(empty === 0, `[${lang}] real mode without Pi: no empty reading fields`)
  await page.screenshot({ path: `${out}/reactor-real-nolink-${lang}.png` })
  check(errors.length === 0, `[${lang}] no JS errors ${errors.join(' | ')}`)
  await context.close()
}
await browser.close()
console.log(failures.length ? `FAILED ${failures.length}` : 'ALL OK')
process.exit(failures.length ? 1 : 0)
