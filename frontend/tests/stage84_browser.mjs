// End-to-end handoff checks against the real local FastAPI server and Chrome.
import { chromium } from 'playwright-core'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import path from 'node:path'

const base = process.env.BIOREACTOR_QA_URL ?? 'http://127.0.0.1:8768'
const output = path.resolve('../reports/stage8_4')
await fs.mkdir(output, { recursive: true })
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  headless: true, args: ['--no-first-run', '--disable-background-networking', '--disable-component-update'] })
const page = await browser.newPage({ viewport: { width: 1366, height: 900 }, locale: 'ru-RU' })
const checks = []; const errors = []; const failed = []
page.on('pageerror', error => errors.push(error.message))
page.on('requestfailed', request => { if (request.failure()?.errorText !== 'net::ERR_ABORTED') failed.push(request.url()) })
await page.route('**/*', route => ['127.0.0.1', 'localhost'].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort())
const check = (name, condition) => { assert.ok(condition, name); checks.push(name) }
try {
  await page.goto(base + '/dashboard/#/substrates', { waitUntil: 'networkidle' })
  await page.locator('.advisor-page h1').waitFor()
  const simpleMode = page.locator('.advisor-page .display-mode button:first-child')
  await simpleMode.waitFor()
  check('Calculator opens in simple mode', await simpleMode.getAttribute('aria-pressed') === 'true')
  await page.locator('.advisor-component select').nth(0).selectOption('food_waste')
  await page.locator('.advisor-component select').nth(1).selectOption('prepared_pulp')
  await page.locator('.advisor-component input[type=number]').first().fill('5')
  await page.locator('.advisor-page form fieldset > label input[type=number]').first().fill('90')
  await page.locator('.advisor-page form fieldset > label input:not([type])').first().fill('KZ-Karaganda-oblast')
  await page.locator('.advisor-page .display-mode button:nth-child(2)').click()
  await page.locator('.advisor-component select').nth(3).selectOption('baek2020-food-pulp')
  await page.locator('.advisor-page input[type=checkbox]').nth(2).check()
  const analysisResponse = page.waitForResponse(response => response.url().endsWith('/api/advisor/analyze') && response.request().method() === 'POST')
  const response = await analysisResponse
  const request = response.request().postDataJSON()
  const analysis = await response.json()
  const scenario = analysis.scenario_results?.[0] ?? analysis
  check('Calculator sends exact 5 kg, profile, 90 L and confirmed region', request.components[0].quantity === 5
    && request.components[0].material === 'food_waste' && request.components[0].reference_profile_id === 'baek2020-food-pulp'
    && request.reactor_total_volume_l === 90 && request.region === 'KZ-Karaganda-oblast' && request.region_confirmed === true)
  check('Scientific response retains its conditional profile evidence', scenario.mixture?.additive_methane_reference_m3?.low > 0
    && scenario.scenario_assumptions?.length > 0)
  await page.screenshot({ path: path.join(output, 'calculator_stage84.png'), fullPage: true })

  const handoffResponse = page.waitForResponse(response => response.url().endsWith('/api/advisor/handoff') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'РџРµСЂРµРґР°С‚СЊ СЃРјРµСЃСЊ РІ С‡Р°С‚' }).click()
  const handoff = await (await handoffResponse).json()
  await page.locator('h1').first().waitFor()
  await page.locator('.conversation-facts').first().waitFor()
  check('Dashboard to chat handoff creates a persisted chat session', Boolean(handoff.session_id))
  const restored = await page.evaluate(async id => (await (await fetch(`/api/dashboard/chat/sessions/${id}`)).json()), handoff.session_id)
  const stored = restored.memory.advanced.inventory[0]
  check('Handoff keeps component mass, unit, physical state and selected profile', stored.material === 'food_waste'
    && stored.quantity === 5 && stored.unit === 'kg' && stored.material_state === 'prepared_pulp'
    && stored.reference_profile_id === 'baek2020-food-pulp')
  check('Handoff keeps confirmed region and nominal reactor capacity', restored.memory.facts.market_region.value === 'KZ-Karaganda-oblast'
    && restored.memory.facts.reactor_total_volume_l.value === 90)

  await page.getByRole('button', { name: 'РћС‚РєСЂС‹С‚СЊ РІ РєР°Р»СЊРєСѓР»СЏС‚РѕСЂРµ' }).click()
  await page.locator('.advisor-page h1').waitFor()
  await page.locator('.display-mode button').nth(1).getAttribute('aria-pressed')
  const selectValues = await page.locator('.advisor-page select').evaluateAll(elements => elements.map(element => element.value))
  const imported = { material: selectValues[0], state: selectValues[1], quantity: await page.locator('.advisor-page input[type="number"]').first().inputValue(),
    profile: selectValues[3], reactor: await page.locator('.advisor-page input[type="number"]').nth(1).inputValue(),
    region: await page.locator('.advisor-page input').evaluateAll(elements => elements.map(element => element.value).find(value => value === 'KZ-Karaganda-oblast')),
    scientific: await page.locator('.advisor-scientific-component[open]').count() > 0 }
  check('Chat to calculator opens scientific mode with original profile details', imported.material === 'food_waste'
    && imported.quantity === '5' && imported.state === 'prepared_pulp' && imported.profile === 'baek2020-food-pulp'
    && imported.reactor === '90' && imported.region === 'KZ-Karaganda-oblast' && imported.scientific === true)
  check('No browser errors or external requests', errors.length === 0 && failed.length === 0)
  await page.screenshot({ path: path.join(output, 'chat_to_calculator_stage84.png'), fullPage: true })
  const result = { passed: true, checks, errors, failed_requests: failed, browser_version: browser.version(), base_url: base,
    transfer: { session_id: handoff.session_id, material: stored.material, quantity: stored.quantity, unit: stored.unit,
      material_state: stored.material_state, profile_id: stored.reference_profile_id,
      region: restored.memory.facts.market_region.value, reactor_total_volume_l: restored.memory.facts.reactor_total_volume_l.value },
    methane_potential_m3: scenario.mixture?.additive_methane_reference_m3 }
  await fs.writeFile(path.join(output, 'browser_checks.json'), JSON.stringify(result, null, 2))
  console.log(JSON.stringify({ passed: true, checks: checks.length, transfer: result.transfer }, null, 2))
} catch (error) {
  await page.screenshot({ path: path.join(output, 'browser_failure_stage84.png'), fullPage: true }).catch(() => {})
  await fs.writeFile(path.join(output, 'browser_failure_stage84.json'), JSON.stringify({ error: String(error), checks, errors, failed }, null, 2))
  throw error
} finally { await browser.close() }



