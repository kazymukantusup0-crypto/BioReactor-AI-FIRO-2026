// «Реактор» in a real browser against a running server in SIMULATOR mode (no hardware):
//   node tests/reactor-browser.mjs            (BASE_URL default http://127.0.0.1:8766)
// Scenarios: readings + source label, heater ON with confirmation, interlock, leak -> heater OFF + full-screen alarm +
// reset only after the gas is gone, no link with the Pi / with the Arduino, jury mode, 3 languages, phone width.
// Screenshots: reports/reactor/*.png. Exit code 1 on any failed check or JS error.
import { chromium } from 'playwright-core'
import fs from 'node:fs'

const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:8766'
const OUT = 'reports/reactor'
fs.mkdirSync(OUT, { recursive: true })
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true })
const failures = []
const errors = []
const check = (ok, text) => { console.log(`${ok ? 'OK  ' : 'FAIL'} ${text}`); if (!ok) failures.push(text) }

async function open(lang = 'ru', width = 1366, height = 900, jury = false) {
  const context = await browser.newContext({ viewport: { width, height } })
  await context.addInitScript(([l, j]) => { try { localStorage.setItem('bioreactor.language', l); localStorage.setItem('bioreactor-reactor-jury', j ? '1' : '0') } catch {} }, [lang, jury])
  const page = await context.newPage()
  page.on('pageerror', e => errors.push(`${lang}: ${e.message}`))
  page.on('response', r => { if (r.status() >= 500) errors.push(`HTTP ${r.status()} ${r.url()}`) })
  await page.goto(`${BASE}/dashboard/#/reactor`)
  await page.getByTestId('rx-reading-temp_c').waitFor()
  await page.waitForTimeout(1500)
  return { page, context }
}
const api = (what, on) => fetch(`${BASE}/api/reactor/simulator`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ what, on }) })
const status = () => fetch(`${BASE}/api/reactor/status`).then(r => r.json())
const relay = (r, on) => fetch(`${BASE}/api/reactor/relay`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ relay: r, on, confirm: true }) }).then(r => r.json())
const overflow = page => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
const shot = (page, name) => page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true })
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))

// clean start: everything off, no simulated failures
for (const what of ['leak', 'usb', 'arduino_silent', 'temp_sensor', 'network']) await api(what, false)
await sleep(2500)
for (const r of ['heat', 'cool', 'pump']) await relay(r, false)
let s = await status()
if (s.leak_latched) { await fetch(`${BASE}/api/reactor/alarm/reset`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{"confirm":true}' }) }

{
  const { page, context } = await open()
  check((await page.getByTestId('rx-source').textContent()).includes('СИМУЛЯТОР'), 'source label: ДАТЧИКИ: СИМУЛЯТОР')
  check((await page.getByTestId('rx-reading-gas_in').textContent()).includes('не «% метана»') || (await page.getByTestId('rx-reading-gas_in').textContent()).includes('НЕ «% метана»'), 'MQ is not «% methane»')
  await shot(page, '01-normal-ru')
  // heater ON through the UI: button -> confirmation -> command
  await page.getByTestId('rx-relay-button-heat').click()
  check(await page.getByTestId('rx-confirm').isVisible(), 'confirmation dialog before switching on')
  await shot(page, '02-confirm')
  await page.getByTestId('rx-confirm-yes').click()
  await page.getByTestId('rx-message').waitFor()
  await page.waitForTimeout(1500)
  check((await page.getByTestId('rx-relay-state-heat').textContent()).includes('ВКЛ'), 'heater ON after confirmation')
  // interlock: cooling button disabled while heating
  check(await page.getByTestId('rx-relay-button-cool').isDisabled(), 'interlock: cooling disabled while the heater is on')
  await page.waitForTimeout(12000)
  check((await page.getByTestId('rx-relay-heat').textContent()).match(/работает (1[0-9]|[2-9][0-9]) с|работает \d+ мин/) !== null, 'relay shows how long it runs')
  await page.getByText('1 час').click()
  await page.waitForTimeout(6000)
  await shot(page, '03-heating-charts')
  // leak: heater OFF automatically, full-screen alarm, reset only when the gas is gone
  await api('leak', true)
  await page.getByTestId('rx-leak-alarm').waitFor({ timeout: 15000 })
  await page.waitForTimeout(1500)
  s = await status()
  check(!s.relays.heat.on && s.leak_latched, 'leak -> heater switched OFF automatically and locked')
  check(await page.getByTestId('rx-leak-reset').isDisabled(), 'reset disabled while still leaking')
  await shot(page, '04-leak-alarm')
  await api('leak', false)
  await page.waitForTimeout(9000)
  check(!(await page.getByTestId('rx-leak-reset').isDisabled()), 'reset enabled after the gas is gone')
  await page.getByText('Свернуть').click()
  check(await page.getByTestId('rx-relay-button-heat').isDisabled(), 'heater stays locked until a person resets')
  await shot(page, '05-leak-collapsed')
  await page.getByTestId('rx-leak-reset').click()
  await page.getByTestId('rx-confirm-yes').click()
  await page.waitForTimeout(2000)
  check(!(await page.getByTestId('rx-relay-button-heat').isDisabled()), 'heater can be switched on again after the reset')
  check(await overflow(page) <= 0, 'no horizontal scroll at 1366')
  // no link with the Arduino (USB pulled)
  await api('usb', true)
  await page.getByText('НЕТ СВЯЗИ С ARDUINO').waitFor({ timeout: 15000 })
  check(await page.getByTestId('rx-relay-button-pump').isDisabled(), 'no Arduino link -> buttons disabled')
  await shot(page, '06-no-arduino')
  await api('usb', false)
  await page.waitForTimeout(6000)
  // no link with the Pi (network cut)
  await api('network', true)
  await page.getByText('НЕТ СВЯЗИ С RASPBERRY PI').waitFor({ timeout: 15000 })
  check(await page.getByTestId('rx-relay-button-heat').isDisabled(), 'no Pi link -> buttons disabled')
  await shot(page, '07-no-pi')
  await api('network', false)
  await page.waitForTimeout(3000)
  await page.getByTestId('rx-journal').scrollIntoViewIfNeeded()
  await shot(page, '08-journal')
  await context.close()
}
{
  const { page, context } = await open('ru', 1280, 720, true)
  await page.waitForTimeout(1000)
  check(await page.getByTestId('rx-jury-panel').isVisible(), 'jury mode panel')
  await page.screenshot({ path: `${OUT}/09-jury-1280x720.png` })
  await context.close()
}
for (const lang of ['kk', 'en']) {
  const { page, context } = await open(lang)
  await shot(page, `10-normal-${lang}`)
  check(await overflow(page) <= 0, `${lang}: no horizontal scroll`)
  await context.close()
}
for (const lang of ['ru', 'kk']) {
  const { page, context } = await open(lang, 390, 844)
  check(await overflow(page) <= 0, `${lang}: phone 390 px without horizontal scroll`)
  await shot(page, `11-phone-${lang}`)
  await context.close()
}
for (const r of ['heat', 'cool', 'pump']) await relay(r, false)
await browser.close()
if (errors.length) { console.log('ERRORS:\n' + errors.join('\n')); failures.push(...errors) }
console.log(failures.length ? `${failures.length} FAILED` : 'ALL OK')
process.exit(failures.length ? 1 : 0)
