// Real installed Chrome, real FastAPI and a QA copy of actual market prices.
// This script never invents prices, sensor readings or economic assumptions.
import { chromium } from 'playwright-core'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import path from 'node:path'

const out = path.resolve('../reports/stage4')
const base = process.env.BIOREACTOR_QA_URL ?? 'http://127.0.0.1:8766'
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true, args: ['--no-first-run', '--disable-background-networking', '--disable-component-update'] })
const context = await browser.newContext({ viewport: { width: 1366, height: 768 }, reducedMotion: 'reduce', locale: 'ru-RU' })
const page = await context.newPage()
const errors = []; const failedRequests = []; const requests = []; const checks = []; const screenshots = []
const check = (name, condition = true) => { assert.ok(condition, name); checks.push(name) }
page.on('pageerror', error => errors.push(error.message))
page.on('requestfailed', req => { if (req.failure()?.errorText !== 'net::ERR_ABORTED') failedRequests.push({ url: req.url(), error: req.failure()?.errorText }) })
page.on('request', req => requests.push({ method: req.method(), url: req.url() }))
await context.route('**/*', route => {
  const url = new URL(route.request().url())
  if (!['127.0.0.1', 'localhost'].includes(url.hostname)) return route.abort()
  return route.continue()
})
const screenshot = async name => {
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }))
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
  await page.screenshot({ path: path.join(out, name), fullPage: true, animations: 'disabled' }); screenshots.push(name)
}
const navigate = async title => { await page.getByRole('button', { name: title, exact: true }).click() }
const noOverflow = async title => check(title + ': no horizontal page overflow', await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1))
try {
  await page.goto(base + '/dashboard/', { waitUntil: 'networkidle' })
  await page.getByText('28 рыночных наблюдений', { exact: true }).waitFor({ timeout: 30000 })
  check('Overview renders real SQLite observation count')
  await page.getByText('SIMULATION / NO LIVE SENSOR DATA', { exact: true }).waitFor()
  check('No live sensor state explicitly labeled')
  await noOverflow('1366 overview'); await screenshot('overview_1366.png')
  await page.setViewportSize({ width: 1920, height: 1080 }); await screenshot('overview_1920.png'); await noOverflow('1920 overview')
  await page.setViewportSize({ width: 1366, height: 768 })

  const demoResponse = await context.request.get(base + '/api/dashboard/demo'); const demo = await demoResponse.json()
  await navigate('Прогноз метана')
  await page.getByLabel('Материал', { exact: false }).selectOption(String(demo.laboratory_example.substrate))
  for (const [name, value] of Object.entries(demo.laboratory_example)) if (name !== 'substrate') await page.locator('#' + name).fill(String(value))
  const predictionResponse = page.waitForResponse(r => r.url().endsWith('/api/dashboard/predict') && r.request().method() === 'POST')
  await page.getByRole('button', { name: 'Рассчитать BMP', exact: true }).click()
  const prediction = await (await predictionResponse).json()
  check('Actual saved estimator predicts via UI', prediction.status === 'ok' && Number.isFinite(prediction.bmp) && prediction.model_called)
  check('No fabricated 90% interval', prediction.uncertainty.interval_90 === null)
  await page.getByText(prediction.model_version, { exact: false }).first().waitFor()
  await page.locator('.prediction-number').waitFor(); await screenshot('prediction_1366.png'); await noOverflow('prediction')

  await navigate('Рыночные данные')
  await page.locator('.market-table').waitFor(); await page.locator('[data-testid="market-chart"]').waitFor()
  check('Real market history is charted', await page.locator('.recharts-line').count() > 0)
  check('Actual Karaganda electricity price shown', (await page.locator('.market-table').innerText()).includes('20,39'))
  await screenshot('market_1366.png'); await noOverflow('market')
  await page.getByRole('button', { name: /Органические удобрения/ }).click()
  await page.getByText('Подтверждённых наблюдений региона нет', { exact: true }).waitFor()
  check('Empty fertilizer category does not invent quotations')
  const updateResponse = page.waitForResponse(r => r.url().includes('/updates?category=organic_fertilizer') && r.request().method() === 'POST')
  await page.getByRole('button', { name: 'Обновить категорию', exact: true }).click()
  const updated = await (await updateResponse).json()
  check('Category refresh uses backend scheduler and creates no fabricated price', updated.inserted === 0 && updated.sources.length > 0)
  await page.getByRole('button', { name: /Электроэнергия/ }).click()
  await page.getByLabel('Регион рынка').selectOption('KZ-Karaganda-Abay-district')
  await page.locator('.price-cell').filter({ hasText: '45,47' }).waitFor()
  check('District filter uses actual KREC district price')
  await page.getByText('Недостаточно истории', { exact: false }).first().waitFor()

  await navigate('Экономика')
  await page.getByRole('button', { name: 'Сравнить сценарии', exact: true }).waitFor()
  await page.locator('#econ-mass_kg').fill('5')
  await page.locator('#econ-feedstock').selectOption('food_waste')
  const economyResponse = page.waitForResponse(r => r.url().endsWith('/scenarios/compare') && r.request().method() === 'POST')
  await page.getByRole('button', { name: 'Сравнить сценарии', exact: true }).click()
  const economy = await (await economyResponse).json()
  check('Incomplete economics is honest, no invented profit', economy.status === 'needs_input' && economy.final_recommendation === null && economy.scenarios.length === 4)
  await page.locator('.scenario-card').first().waitFor()
  await screenshot('economics_1366.png'); await noOverflow('economics')

  await navigate('AI Chat')
  await page.locator('#chat-input').fill(demo.question)
  const agentResponse = page.waitForResponse(r => /\/chat\/sessions\/[^/]+\/messages$/.test(r.url()) && r.request().method() === 'POST', { timeout: 130000 })
  await page.getByRole('button', { name: 'Отправить сообщение' }).click()
  check('Duplicate chat submission prevented while running', await page.getByRole('button', { name: 'Отправить сообщение' }).isDisabled())
  const reply = await (await agentResponse).json()
  await page.locator('.tool-trace').waitFor({ timeout: 130000 })
  check('Tool trace exactly matches actual backend calls', await page.locator('.trace-chain code').count() === reply.tools.length)
  check('Agent refuses unsupported food waste BMP', reply.tools.some(t => t.tool === 'predict_bmp' && t.result.model_called === false))
  check('Agent calls market economics', reply.tools.some(t => t.tool === 'compare_market_scenarios'))
  check('Real source links displayed', await page.locator('.source-links a').count() > 0)
  await screenshot('chat_1366.png'); await noOverflow('chat')
  await page.reload({ waitUntil: 'networkidle' }); await page.locator('.tool-trace').waitFor()
  check('Conversation restored from SQLite after reload', await page.locator('.chat-turn').count() === 1)
  const messageRequests = requests.filter(r => r.method === 'POST' && /\/chat\/sessions\/[^/]+\/messages$/.test(r.url))
  check('One chat request, one submitted message', messageRequests.length === 1)

  await navigate('Научная аналитика')
  await page.getByText('53,92', { exact: true }).waitFor()
  await page.getByText('80,38', { exact: true }).waitFor()
  await page.locator('.scientific-figure img').waitFor()
  await page.waitForFunction(() => { const image = document.querySelector('.scientific-figure img'); return image instanceof HTMLImageElement && image.naturalWidth > 0 })
  check('Scientific metrics and original report figure loaded')
  check('Independent study limitation shown', (await page.locator('main').innerText()).includes('не независимая проверка'))
  await screenshot('science_1366.png'); await noOverflow('science')

  await navigate('Реактор')
  await page.getByRole('button', { name: 'Симуляция схемы' }).click()
  await page.getByRole('button', { name: 'Следующий шаг' }).click()
  check('Simulation is a labeled signal diagram, no numeric readings', await page.locator('.simulation-control').isVisible())
  check('Physical actuator controls not offered', await page.getByRole('button', { name: /Включить насос|Включить нагрев|Отправить команду/ }).count() === 0)
  await screenshot('reactor_1366.png'); await noOverflow('reactor')

  await navigate('Состояние системы')
  await page.getByText('Соединение установлено', { exact: true }).waitFor({ timeout: 15000 })
  check('Backend diagnostics rendered')
  await screenshot('system_1366.png'); await noOverflow('system')

  await page.getByRole('button', { name: /FIRO 2026/ }).click()
  await page.getByRole('button', { name: 'Открыть RECORDED DEMO' }).click()
  await page.getByText('RECORDED DEMO · архив', { exact: true }).waitFor()
  check('Recorded demo clearly separated and labeled')
  await noOverflow('FIRO demo'); await screenshot('firo_1366.png')
  await page.getByRole('button', { name: 'Открыть прогноз', exact: true }).click()
  await page.getByText('LAB EXAMPLE', { exact: true }).waitFor()
  check('Laboratory example is explicitly labeled before a live prediction')

  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByRole('button', { name: 'Открыть меню' }).click()
  await navigate('Обзор'); await page.getByText('28 рыночных наблюдений', { exact: true }).waitFor()
  await screenshot('overview_mobile.png'); await noOverflow('mobile overview')
  check('No browser internet requests needed', requests.every(r => ['127.0.0.1', 'localhost'].includes(new URL(r.url).hostname)))
  check('No uncaught browser errors', errors.length === 0)
  check('No failed browser requests', failedRequests.length === 0)
  const result = { passed: true, browser: await browser.version(), checks, screenshots, viewport_sizes: ['1366x768', '1920x1080', '390x844'], external_requests_blocked: true, errors, failedRequests, actual_prediction: prediction, actual_economics: economy, actual_agent: reply, http_requests: requests.length, base_url: base }
  await fs.writeFile(path.join(out, 'browser_checks.json'), JSON.stringify(result, null, 2))
  console.log(JSON.stringify({ passed: true, checks: checks.length, screenshots, agent_mode: reply.mode, requests: requests.length, errors }, null, 2))
} catch (error) {
  await screenshot('browser_failure.png')
  await fs.writeFile(path.join(out, 'browser_failure.json'), JSON.stringify({ error: String(error), checks, errors, failedRequests, last_url: page.url() }, null, 2))
  throw error
} finally { await browser.close() }
