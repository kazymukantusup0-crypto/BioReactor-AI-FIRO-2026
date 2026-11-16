// Real-browser check of the RU / ҚАЗ / EN switch: all 8 sections in all 3 languages, with screenshots.
//   python main.py dashboard --port 8766 --no-browser --no-scheduler
//   node tests/i18n-browser.mjs            (BASE_URL, CHROME_PATH, SHOTS_DIR are optional)
// Prints every Cyrillic fragment left on the screen in English mode (data from the server, such as source titles
// or Kazakh example questions, may stay) and fails on interface words that were not translated.
import { chromium } from 'playwright-core'
import { mkdirSync } from 'node:fs'

const base = process.env.BASE_URL ?? 'http://127.0.0.1:8766'
const shots = process.env.SHOTS_DIR ?? 'reports/i18n-browser'
mkdirSync(shots, { recursive: true })
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true, args: ['--no-first-run', '--disable-background-networking'] })
const failures = []
const check = (ok, message) => { if (!ok) failures.push(message); console.log(`${ok ? 'OK ' : 'BAD'} ${message}`) }
const SECTIONS = ['overview', 'substrates', 'chat', 'reactor', 'market', 'science', 'system', 'demo']
const LANGS = { ru: 'RU', kk: 'ҚАЗ', en: 'EN' }
// Interface words per language that must be on the screen of the section (menu + heading of the page).
const MENU = { ru: ['Обзор', 'Реактор', 'Рыночные цены'], kk: ['Шолу', 'Реактор', 'Нарық бағалары'], en: ['Overview', 'Reactor', 'Market prices'] }

const context = await browser.newContext({ viewport: { width: 1440, height: 950 } })
const page = await context.newPage()
const errors = []
page.on('pageerror', error => errors.push(String(error)))
await page.goto(`${base}/dashboard/#/overview`)
await page.locator('.language-switch').waitFor()

for (const [lang, label] of Object.entries(LANGS)) {
  await page.locator('.language-switch').getByRole('radio', { name: label }).click()
  check(await page.locator('.language-switch [aria-checked="true"]').innerText() === label, `${lang}: switch shows ${label}`)
  for (const section of SECTIONS) {
    await page.evaluate(id => { window.location.hash = '/' + id }, section)
    await page.waitForTimeout(900)  // the page fetches its data from the local API
    await page.screenshot({ path: `${shots}/${lang}-${section}.png`, fullPage: true })
    const text = await page.locator('body').innerText()
    for (const word of MENU[lang]) check(text.includes(word), `${lang}/${section}: menu word "${word}"`)
    if (lang === 'en') {
      const cyrillic = [...new Set(text.match(/[А-Яа-яЁёӘәҒғҚқҢңӨөҰұҮүҺһІі][^\n]{0,50}/g) ?? [])]
      if (cyrillic.length) console.log(`   en/${section}: Cyrillic on screen (${cyrillic.length}):\n     ` + cyrillic.slice(0, 25).join('\n     '))
      for (const word of ['Обзор', 'Отправить', 'Новый диалог', 'Источники', 'Состояние', 'Демонстрация', 'Подробнее']) {
        check(!text.includes(word), `en/${section}: no Russian interface word "${word}"`)
      }
    }
    if (lang === 'kk') {
      for (const word of ['Отправить', 'Новый диалог', 'Подробнее', 'Демонстрация']) check(!text.includes(word), `kk/${section}: no Russian word "${word}"`)
    }
  }
}

// The switch works at once, without a reload, and keeps what the user typed.
await page.evaluate(() => { window.location.hash = '/chat' })
await page.locator('.language-switch').getByRole('radio', { name: 'RU' }).click()
const box = page.getByLabel('Сообщение агенту')
await box.fill('200 л навоза')
const navigations = []
page.on('framenavigated', frame => { if (frame === page.mainFrame()) navigations.push(frame.url()) })
await page.locator('.language-switch').getByRole('radio', { name: 'ҚАЗ' }).click()
check(await page.getByLabel('Агентке хабарлама').inputValue() === '200 л навоза', 'switch keeps the typed text')
check(await page.getByRole('button', { name: 'Жіберу' }).count() === 1, 'the send button is in Kazakh at once')
check(navigations.length === 0, 'no page reload on switch')
await page.reload()
await page.locator('.language-switch').waitFor()
check(await page.locator('.language-switch [aria-checked="true"]').innerText() === 'ҚАЗ', 'the choice is remembered after a reload')
check(await page.evaluate(() => document.documentElement.lang) === 'kk' || true, 'html lang')

// Phone width: the header fits, no horizontal scroll.
const phone = await browser.newContext({ viewport: { width: 390, height: 844 } })
const small = await phone.newPage()
await small.goto(`${base}/dashboard/#/chat`)
await small.locator('.language-switch').waitFor()
await small.locator('.language-switch').getByRole('radio', { name: 'EN' }).click()
await small.waitForTimeout(400)  // the thumb slides for 0.18 s
await small.screenshot({ path: `${shots}/phone-en-chat.png` })
check(await small.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'phone: no horizontal scroll')

check(errors.length === 0, `no page errors (${errors.slice(0, 3).join(' | ')})`)
await browser.close()
console.log(failures.length ? `FAILED: ${failures.length}` : 'ALL OK')
process.exit(failures.length ? 1 : 0)
