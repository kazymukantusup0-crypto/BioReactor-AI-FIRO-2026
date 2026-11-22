// Screenshot of the AI chat with a real dialogue (thinking feed + answer), any language.
// Usage: node tests/design-chat-shot.mjs <out-prefix> [lang=ru] [llm=off]   (BASE_URL default http://127.0.0.1:8766)
import { chromium } from 'playwright-core'
const [prefix = 'reports/chat', lang = 'ru', llm = 'off'] = process.argv.slice(2)
const questions = { ru: 'У меня 200 литров коровьего навоза, сколько будет газа?', kk: 'Сиыр көңі 200 литр, қанша газ болады?', en: 'I have 200 litres of cow manure, how much gas will I get?' }
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true })
const context = await browser.newContext({ viewport: { width: 1366, height: 768 } })
await context.addInitScript(l => { try { localStorage.setItem('bioreactor.language', l) } catch {} }, lang)
const page = await context.newPage()
const errors = []
page.on('pageerror', e => errors.push(e.message))
await page.goto(`${process.env.BASE_URL ?? 'http://127.0.0.1:8766'}/dashboard/#/chat`, { waitUntil: 'networkidle' })
const noLlm = page.locator('.ac-topline input[type=checkbox], .ac-header input[type=checkbox], main input[type=checkbox]').first()
if (llm === 'off' && await noLlm.count() && !(await noLlm.isChecked())) await noLlm.check()
await page.locator('textarea').fill(questions[lang] ?? questions.ru)
await page.locator('button[type=submit]').click()
await page.waitForTimeout(700)
await page.screenshot({ path: `${prefix}-thinking.png` })
await page.locator('.ac-answer').first().waitFor({ timeout: 120000 })
await page.waitForTimeout(600)
await page.screenshot({ path: `${prefix}-answer.png`, fullPage: true })
console.log(prefix, errors.length ? 'ERRORS: ' + errors.join(' | ') : 'no errors')
await browser.close()
