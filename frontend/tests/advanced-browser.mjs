import {chromium} from 'playwright-core'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
assert.equal(process.env.BIOREACTOR_QA_ISOLATED,'1')
const base=process.env.BIOREACTOR_QA_URL,out='../reports/stage8_0',checks=[],errors=[]
const check=(name,passed=true)=>{assert.ok(passed,name);checks.push(name);console.log(name)}
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true,args:['--no-first-run','--disable-background-networking']})
let passed=false
try{
 const context=await browser.newContext({viewport:{width:1440,height:1000},locale:'ru-RU'}),page=await context.newPage()
 page.on('pageerror',e=>errors.push(e.message));await context.route('**/*',r=>['127.0.0.1','localhost'].includes(new URL(r.request().url()).hostname)?r.continue():r.abort())
 await page.goto(base+'/dashboard/#/substrates');await page.getByLabel('Количество 1',{exact:true}).fill('156');await page.getByLabel('Единицы 1',{exact:true}).selectOption('L');await page.getByLabel('Состояние 1',{exact:true}).selectOption('bedded')
 await page.getByLabel('Степень разложения 1',{exact:true}).selectOption('fresh');await page.getByLabel('Подстилка 1',{exact:true}).selectOption('sawdust')
 check('Independent animal, decay, bedding and data-mode controls present',await page.getByLabel('Вид животного 1',{exact:true}).count()===1&&await page.getByLabel('Данные 1',{exact:true}).count()===1)
 const response=page.waitForResponse(r=>r.url().endsWith('/api/advisor/analyze')&&r.request().method()==='POST');await page.getByRole('button',{name:'Получить оценку',exact:true}).click();const result=await(await response).json()
 check('Real form sends independent axes',result.request.components[0].physical_state==='bedded'&&result.request.components[0].decay_state==='fresh'&&result.request.components[0].bedding==='sawdust')
 check('Real form density is bedded-manure reference',Math.abs(result.mixture.total_wet_mass_kg.low-110.76)<1e-8)
 await page.getByTestId('advisor-methane').waitFor();check('Litres to kilograms shown',/110[.,]76/.test(await page.getByTestId('conversion-summary').innerText()))
 check('Scientific details initially closed',await page.locator('.compact-science').getAttribute('open')===null)
 await page.screenshot({path:out+'/substrates_1440.png',fullPage:true});await page.setViewportSize({width:390,height:844});check('Mobile does not overflow',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await page.screenshot({path:out+'/substrates_390.png',fullPage:true})
 await page.setViewportSize({width:1440,height:1000});await page.goto(base+'/dashboard/#/chat');await page.evaluate(id=>localStorage.setItem('bioreactor_chat_session_v4',id),process.env.BIOREACTOR_QA_SESSION);await page.reload();await page.getByTestId('conversational-answer').last().waitFor()
 check('Actual pending task loaded',await page.getByTestId('conversational-answer').count()>=1)
 check('Clarification options rendered',await page.locator('.clarification-options').getByRole('button',{name:'Коровий',exact:true}).count()>=1)
 const resumed=page.waitForResponse(r=>r.url().endsWith('/messages')&&r.request().method()==='POST');await page.locator('.clarification-options').getByRole('button',{name:'Коровий',exact:true}).click();const resumedReply=await(await resumed).json()
 check('Clicking species resumes all requested calculations',resumedReply.pending_question===null&&resumedReply.tools.length===3&&resumedReply.answer.includes('электричества')&&resumedReply.answer.includes('Чистая выгода'))
 await page.getByTestId('advanced-inventory-facts').waitFor();check('Sidebar shows confirmed 156 L instead of empty facts',/156 л/.test(await page.getByTestId('advanced-inventory-facts').innerText()))
 check('No model MAE in prose',!/MAE|CatBoost|Nested CV/.test(await page.locator('.conversation-prose').allInnerTexts().then(x=>x.join(' '))))
 check('Technical trace stays closed',await page.locator('.conversation-technical').last().getAttribute('open')===null)
 await page.getByLabel('Сообщение агенту').fill('А если 200 литров?');const follow=page.waitForResponse(r=>r.url().endsWith('/messages')&&r.request().method()==='POST');await page.getByRole('button',{name:'Отправить сообщение',exact:true}).click();const reply=await(await follow).json()
 check('Browser edit preserves original 156 L and original goals',reply.memory.advanced.inventory[0].quantity===156&&reply.memory.advanced.scenario[0].quantity===200&&reply.memory.advanced.task.goals.includes('economics'))
 check('Browser reply warns about completely occupied vessel',reply.answer.includes('места нет'))
 check('Sidebar separates original stock from 200 L scenario',/156 л/.test(await page.getByTestId('advanced-inventory-facts').innerText())&&/200 л/.test(await page.getByTestId('advanced-inventory-facts').innerText()))
 await page.screenshot({path:out+'/chat_1440.png',fullPage:true});check('No JavaScript errors',errors.length===0);passed=true
}finally{await fs.writeFile(out+'/browser_results.json',JSON.stringify({passed,checks,errors},null,2));await browser.close()}
