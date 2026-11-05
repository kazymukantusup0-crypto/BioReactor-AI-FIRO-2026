// Real Chrome, real local API; all writes confined to v7 verification backup.
import { chromium } from 'playwright-core'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
assert.equal(process.env.BIOREACTOR_QA_ISOLATED,'1')
const base=process.env.BIOREACTOR_QA_URL
assert.match(base,/^http:\/\/127\.0\.0\.1:\d+$/)
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true,args:['--no-first-run','--disable-background-networking']})
const checks=[],errors=[]
try {
 const context=await browser.newContext({viewport:{width:1366,height:900},locale:'ru-RU',reducedMotion:'reduce'})
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message))
 await page.goto(base+'/dashboard/#/chat')
 await page.evaluate(id=>{localStorage.setItem('bioreactor-chat-session',id)},process.env.BIOREACTOR_QA_SESSION)
 // Discover the existing session storage key from the actual application, not a separate fake UI.
 const keys=await page.evaluate(()=>Object.keys(localStorage))
 const source=await fs.readFile('src/pages/Chat.tsx','utf8');const key=source.match(/SESSION_KEY\s*=\s*['"]([^'"]+)/)?.[1]
 assert.ok(key);await page.evaluate(({key,id})=>localStorage.setItem(key,id),{key,id:process.env.BIOREACTOR_QA_SESSION})
 await page.reload();await page.getByTestId('conversational-answer').first().waitFor({timeout:30000})
 assert.ok(await page.getByText('HYPOTHETICAL_SCENARIO',{exact:true}).count());checks.push('Hypothetical result badge visible')
 assert.ok(await page.getByText('LITERATURE_ESTIMATE',{exact:true}).count());checks.push('Literature result badge visible')
 assert.ok(await page.getByRole('link',{name:/Moderate thermal/}).count());checks.push('Primary DOI source link visible')
 assert.ok((await page.locator('.conversation-prose').allTextContents()).some(t=>t.includes('2.92')&&t.includes('4.11')));checks.push('Real calculated methane range rendered')
 await page.screenshot({path:'../reports/stage7/chat_research_1366.png',fullPage:true})
 await page.getByLabel('Сообщение агенту').fill('Навозная жижа')
 const response=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/messages'),{timeout:120000})
 await page.getByRole('button',{name:'Отправить сообщение'}).click()
 const reply=await (await response).json();assert.equal(reply.conversation_version,'7');assert.equal(reply.technical_metadata.research_result.result_level,'LITERATURE_ESTIMATE');checks.push('Actual Chrome sends persisted v7 research turn')
 await page.setViewportSize({width:390,height:844});await page.reload();await page.getByTestId('conversational-answer').first().waitFor()
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));checks.push('Mobile chat has no page overflow')
 await page.screenshot({path:'../reports/stage7/chat_research_390.png',fullPage:false})
 assert.equal(errors.length,0);checks.push('No browser page errors')
 await fs.writeFile('../reports/stage7/browser-results.json',JSON.stringify({checks,errors,passed:true},null,2))
 console.log(JSON.stringify({passed:true,checks:checks.length}))
} finally {await browser.close()}
