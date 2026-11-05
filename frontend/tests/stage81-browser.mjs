import { chromium } from 'playwright-core'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

assert.equal(process.env.BIOREACTOR_QA_ISOLATED, '1', 'Refuse to run against the production database')
const base = process.env.BIOREACTOR_QA_URL
assert.ok(base, 'Set BIOREACTOR_QA_URL to the isolated local server')
const report = fileURLToPath(new URL('../../reports/stage8_1/', import.meta.url))
const screenshots = path.join(report, 'screenshots')
await fs.mkdir(screenshots, { recursive: true })
const browser = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true, args: ['--no-first-run', '--disable-background-networking'] })
const errors = []
const checks = []
const check = (name, ok) => { assert.ok(ok, name); checks.push(name); console.log(`PASS ${name}`) }
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, locale: 'ru-RU' })
  const page = await context.newPage()
  page.on('pageerror', error => errors.push(error.message))
  await page.route('**/*', route => ['127.0.0.1', 'localhost'].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort())
  await page.goto(`${base}/dashboard/#/substrates`)
  await page.getByLabel('Сырьё 1').waitFor()
  const apiCatalog = await page.evaluate(async () => (await fetch('/api/advisor/catalog')).json())
  check('API serves separate swine and poultry material definitions', apiCatalog.materials.some(x => x.id === 'swine_manure') && apiCatalog.materials.some(x => x.id === 'poultry_manure'))

  await page.getByLabel('Сырьё 1').selectOption('swine_manure')
  await page.getByLabel('Состояние 1').selectOption('slurry')
  await page.getByLabel('Количество 1').fill('100')
  await page.getByLabel('Единицы 1').selectOption('L')
  await page.getByLabel('Состояние 1').selectOption('slurry')
  check('Swine liquid state and volume unit are editable', await page.getByLabel('Единицы 1').inputValue() === 'L')

  await page.getByRole('button', { name: 'Добавить материал' }).click()
  await page.getByLabel('Сырьё 2').selectOption('poultry_manure')
  await page.getByLabel('Состояние 2').selectOption('fresh_solid')
  await page.getByLabel('Тип птичьего помёта 2').selectOption('layer')
  const profile = page.getByLabel('Научный профиль 2')
  await profile.waitFor()
  check('Layer subtype offers its specific primary-study profile', (await profile.locator('option').allTextContents()).some(x => x.includes('ramos2019-layers-HD-sample1')))
  await profile.selectOption('ramos2019-layers-HD-sample1')
  await page.getByLabel('Количество 2').fill('20')
  await page.getByRole('button', { name: 'Получить оценку' }).click()
  await page.getByTestId('advisor-results').waitFor()
  const analyses = await page.evaluate(async () => (await fetch('/api/advisor/runs')).json())
  check('Mixture analysis reaches the backend with two components', analyses.runs.length === 1)
  const savedRequest = await page.evaluate(async () => (await fetch('/api/advisor/runs')).json())
  check('Literature selection is explicit and both rows remain in analysis', savedRequest.runs[0].request.components.length === 2 && savedRequest.runs[0].request.components[1].reference_profile_id === 'ramos2019-layers-HD-sample1')

  await page.screenshot({ path: path.join(screenshots, 'substrate-mixture-desktop.png'), fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  check('Mobile page has no horizontal overflow', await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1))
  await page.screenshot({ path: path.join(screenshots, 'substrate-mixture-mobile.png'), fullPage: true })
  await page.setViewportSize({ width: 1440, height: 1000 })

  await page.getByLabel('Название смеси для сохранения').fill('QA: swine liquid + laying-hen sample')
  await page.getByRole('button', { name: 'Сохранить смесь' }).click()
  await page.getByLabel('Сохранённые смеси').selectOption({ index: 1 })
  await page.getByRole('button', { name: 'Загрузить смесь' }).click()
  check('Saved mixture reloads with both rows', await page.getByLabel('Сырьё 2').inputValue() === 'poultry_manure' && await page.getByLabel('Научный профиль 2').inputValue() === 'ramos2019-layers-HD-sample1')

  await page.getByRole('button', { name: 'Передать смесь в чат' }).click()
  const messageBox = page.getByLabel('Сообщение агенту')
  await messageBox.waitFor()
  check('Handoff preloads the economics question in the chat composer', (await messageBox.inputValue()).includes('экономику'))
  const handoffReply = page.waitForResponse(response => response.url().endsWith('/messages') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Отправить сообщение' }).click()
  await handoffReply
  await page.getByTestId('conversational-answer').last().waitFor()
  check('Agent handoff loads a conversation session', await page.getByTestId('conversational-answer').count() > 0)
  const state = await page.evaluate(async () => {
    const id = localStorage.getItem('bioreactor_chat_session_v4')
    return (await (await fetch(`/api/dashboard/chat/sessions/${id}`)).json()).memory.advanced.inventory
  })
  check('Agent receives original units, species, subtype and profile ID', state.length === 2 && state[0].unit === 'L' && state[0].animal === 'pig' && state[1].poultry_type === 'layer' && state[1].reference_profile_id === 'ramos2019-layers-HD-sample1')
  check('No browser JavaScript errors', errors.length === 0)
  await fs.writeFile(path.join(report, 'browser_results.json'), JSON.stringify({ passed: true, checks, errors }, null, 2))
} finally {
  await browser.close()
}
