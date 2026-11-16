// Real-browser check of the agent v10 chat against a running dashboard and the real local LLM.
//   python main.py dashboard --port 8766 --no-browser --no-scheduler
//   node tests/agent-chat-browser.mjs            (BASE_URL, CHROME_PATH, SHOTS_DIR are optional)
import { chromium } from 'playwright-core'
import { mkdirSync } from 'node:fs'

const base = process.env.BASE_URL ?? 'http://127.0.0.1:8766'
const shots = process.env.SHOTS_DIR ?? 'reports/agent-chat-browser'
mkdirSync(shots, { recursive: true })
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true, args: ['--no-first-run', '--disable-background-networking'] })
const failures = []
const check = (ok, message) => { if (!ok) failures.push(message); console.log(`${ok ? 'OK ' : 'BAD'} ${message}`) }

const context = await browser.newContext({ viewport: { width: 1440, height: 950 } })
const page = await context.newPage()
const errors = []
page.on('pageerror', error => errors.push(String(error)))
await page.goto(`${base}/dashboard/#/chat`)
await page.getByRole('button', { name: 'Новый диалог' }).click()
await page.getByRole('heading', { name: 'Спросите про свою установку' }).waitFor()
await page.screenshot({ path: `${shots}/1-empty.png` })

const question = process.env.QUESTION ?? 'У меня 200 литров коровьего навоза, сколько будет газа?'
await page.getByLabel('Сообщение агенту').fill(question)
await page.getByRole('button', { name: 'Отправить' }).click()
await page.getByText('Понял вопрос').first().waitFor({ timeout: 10000 })
await page.screenshot({ path: `${shots}/2-thinking.png` })
await page.locator('.ac-answer').first().waitFor({ timeout: 90000 })
await page.screenshot({ path: `${shots}/3-answer-farmer.png`, fullPage: true })
check(await page.locator('.ac-card').count() >= 1, 'number cards are shown')
check(await page.getByText(/Числа сверены|заменён шаблоном/).count() === 1, 'verification badge is shown')
check((await page.locator('.ac-facts').innerText()).includes('КРС'), 'facts panel shows the feedstock (told or demo default)')

await page.getByRole('button', { name: /Режим жюри/ }).click()
await page.waitForTimeout(400)
await page.screenshot({ path: `${shots}/4-answer-jury.png`, fullPage: true })
check(await page.locator('.ac-feed-detail').count() >= 2, 'jury mode shows step details')

const phone = await context.newPage()
await phone.setViewportSize({ width: 390, height: 844 })
await phone.goto(`${base}/dashboard/#/chat`)
await phone.locator('.ac-answer').first().waitFor({ timeout: 10000 })
await phone.screenshot({ path: `${shots}/5-phone.png`, fullPage: true })
const overflow = await phone.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
check(overflow <= 1, `no horizontal scroll on a phone (overflow ${overflow}px)`)

check(errors.length === 0, `no page errors ${errors.join(' | ')}`)
await browser.close()
if (failures.length) { console.error(failures); process.exit(1) }
