// «Реактор» in a real browser against a running server in SIMULATOR mode (no hardware):
//   BIOREACTOR_SENSORS=simulator  main.py dashboard --port 8766 --no-browser --no-scheduler
//   node tests/reactor-browser.mjs            (BASE_URL default http://127.0.0.1:8766)
// Scenarios (firmware bioreactor-1.0): readings + source label, heater and auger ON with confirmation, interlock,
// threshold change with confirmation, E-STOP in one click + reset, AUTO, leak -> everything OFF + full-screen alarm +
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
const post = (path, body) => fetch(`${BASE}/api/reactor/${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(r => r.json())
const api = (what, on) => post('simulator', { what, on })
const status = () => fetch(`${BASE}/api/reactor/status`).then(r => r.json())
const relay = (r, on) => post('relay', { relay: r, on, confirm: true })
const overflow = page => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
const shot = (page, name) => page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true })
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))

// clean start: no simulated failures, alarms reset, manual mode, everything off, warm-up over
for (const what of ['leak', 'usb', 'arduino_silent', 'temp_sensor', 'network']) await api(what, false)
await sleep(2500)
await post('alarm/reset', { confirm: true })
await post('auto', { on: false, confirm: true })
for (const r of ['heat', 'cool', 'pump', 'auger']) await relay(r, false)
await post('limit', { name: 'temp_min', value: 35, confirm: true })
for (let i = 0; i < 40 && (await status()).arduino_alarms?.warmup; i++) await sleep(1000)
let s = await status()

{
  const { page, context } = await open()
  check((await page.getByTestId('rx-source').textContent()).includes('СИМУЛЯТОР'), 'source label: ДАТЧИКИ: СИМУЛЯТОР')
  check((await page.getByTestId('rx-reading-gas_in').textContent()).includes('сырое значение 0–1023'), 'gas is a raw indicator 0-1023, not ppm')
  check(await page.getByTestId('rx-estop').isEnabled(), 'E-STOP button visible and enabled')
  await shot(page, '01-normal-ru')
  // heater ON through the UI: button -> confirmation -> command
  await page.getByTestId('rx-relay-button-heat').click()
  check(await page.getByTestId('rx-confirm').isVisible(), 'confirmation dialog before switching on')
  await shot(page, '02-confirm')
  await page.getByTestId('rx-confirm-yes').click()
  await page.getByTestId('rx-message').waitFor()
  await page.waitForTimeout(1500)
  check((await page.getByTestId('rx-relay-state-heat').textContent()).includes('ВКЛ'), 'heater ON after confirmation')
  check((await page.getByTestId('rx-relay-who-heat').textContent()).includes('с ноутбука'), 'relay says it was switched on from the laptop')
  check(await page.getByTestId('rx-relay-button-cool').isDisabled(), 'interlock: cooling disabled while the heater is on')
  // auger
  await page.getByTestId('rx-relay-button-auger').click()
  await page.getByTestId('rx-confirm-yes').click()
  await page.waitForTimeout(1500)
  check((await page.getByTestId('rx-relay-state-auger').textContent()).includes('ВКЛ'), 'auger ON after confirmation')
  await page.waitForTimeout(10000)
  check((await page.getByTestId('rx-relay-heat').textContent()).match(/работает (1[0-9]|[2-9][0-9]) с|работает \d+ мин/) !== null, 'relay shows how long it runs')
  // threshold with confirmation
  await page.getByTestId('rx-limit-input-temp_min').fill('36')
  await page.getByTestId('rx-limit-save-temp_min').click()
  check((await page.getByTestId('rx-confirm').textContent()).includes('станет 36.0 °C'), 'threshold change asks for confirmation')
  await page.getByTestId('rx-confirm-yes').click()
  await page.waitForTimeout(2000)
  check((await status()).limits.temp_min === 36, 'Temp Min saved in the (virtual) Arduino')
  await page.getByTestId('rx-limits').scrollIntoViewIfNeeded()
  await shot(page, '03-limits')
  await post('limit', { name: 'temp_min', value: 35, confirm: true })
  // E-STOP: one click
  await page.getByTestId('rx-estop').click()
  await page.getByTestId('rx-estop-alarm').waitFor({ timeout: 8000 })
  s = await status()
  check(!Object.values(s.relays).some(r => r.on) && s.auto === false && s.arduino_alarms.estop, 'E-STOP: every relay off, AUTO off, latched')
  await shot(page, '04-estop')
  await page.getByTestId('rx-alarm-reset').click()
  await page.getByTestId('rx-confirm-yes').click()
  await page.waitForTimeout(2500)
  check(!(await status()).arduino_alarms.estop, 'E-STOP cleared by a person')
  // AUTO through the UI
  await page.getByTestId('rx-mode-button').click()
  await page.getByTestId('rx-confirm-yes').click()
  await page.waitForTimeout(2500)
  check((await page.getByTestId('rx-mode-state').textContent()).includes('АВТО'), 'AUTO switched on with confirmation')
  await page.getByText('1 час').click()
  await page.waitForTimeout(5000)
  await shot(page, '05-auto-charts')
  // leak: everything OFF, full-screen alarm, reset only when the gas is gone
  await api('leak', true)
  await page.getByTestId('rx-leak-alarm').waitFor({ timeout: 15000 })
  await page.waitForTimeout(1500)
  s = await status()
  check(!Object.values(s.relays).some(r => r.on) && s.arduino_alarms.leak && s.auto === false, 'leak -> every relay and AUTO off, latched')
  check(await page.getByTestId('rx-alarm-reset').isDisabled(), 'reset disabled while still leaking')
  await shot(page, '06-leak-alarm')
  await api('leak', false)
  await page.waitForTimeout(9000)
  check(!(await page.getByTestId('rx-alarm-reset').isDisabled()), 'reset enabled after the gas is gone')
  await page.getByText('Свернуть').click()
  check(await page.getByTestId('rx-relay-button-heat').isDisabled(), 'relays stay locked until a person resets')
  await page.getByTestId('rx-alarm-reset').click()
  await page.getByTestId('rx-confirm-yes').click()
  await page.waitForTimeout(2500)
  check(!(await page.getByTestId('rx-relay-button-heat').isDisabled()), 'heater can be switched on again after the reset')
  check(await overflow(page) <= 0, 'no horizontal scroll at 1366')
  // no link with the Arduino (USB pulled)
  await api('usb', true)
  await page.getByText('НЕТ СВЯЗИ С ARDUINO').waitFor({ timeout: 15000 })
  check(await page.getByTestId('rx-relay-button-pump').isDisabled(), 'no Arduino link -> buttons disabled')
  await shot(page, '07-no-arduino')
  await api('usb', false)
  await page.waitForTimeout(6000)
  // no link with the Pi (network cut)
  await api('network', true)
  await page.getByText('НЕТ СВЯЗИ С RASPBERRY PI').waitFor({ timeout: 15000 })
  check(await page.getByTestId('rx-relay-button-heat').isDisabled(), 'no Pi link -> buttons disabled')
  await shot(page, '08-no-pi')
  await api('network', false)
  await page.waitForTimeout(3000)
  await page.getByTestId('rx-journal').scrollIntoViewIfNeeded()
  await shot(page, '09-journal')
  await context.close()
}
{
  const { page, context } = await open('ru', 1280, 720, true)
  await page.waitForTimeout(1000)
  check(await page.getByTestId('rx-jury-panel').isVisible(), 'jury mode panel')
  await page.screenshot({ path: `${OUT}/10-jury-1280x720.png` })
  await context.close()
}
for (const lang of ['kk', 'en']) {
  const { page, context } = await open(lang)
  await shot(page, `11-normal-${lang}`)
  check(await overflow(page) <= 0, `${lang}: no horizontal scroll`)
  await context.close()
}
for (const lang of ['ru', 'kk']) {
  const { page, context } = await open(lang, 390, 844)
  check(await overflow(page) <= 0, `${lang}: phone 390 px without horizontal scroll`)
  await shot(page, `12-phone-${lang}`)
  await context.close()
}
await post('alarm/reset', { confirm: true })
for (const r of ['heat', 'cool', 'pump', 'auger']) await relay(r, false)
await browser.close()
if (errors.length) { console.log('ERRORS:\n' + errors.join('\n')); failures.push(...errors) }
console.log(failures.length ? `${failures.length} FAILED` : 'ALL OK')
process.exit(failures.length ? 1 : 0)
