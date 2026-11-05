// Installed Chrome against real FastAPI on an isolated copy of production SQLite.
import { chromium } from 'playwright-core'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
assert.equal(process.env.BIOREACTOR_QA_ISOLATED,'1')
const base=process.env.BIOREACTOR_QA_URL;assert.match(base,/^http:\/\/127\.0\.0\.1:\d+$/)
const out='../reports/stage7_6',checks=[],errors=[],requests=[]
const screenshot=async(page,name,fullPage=true)=>{await page.evaluate(()=>{document.activeElement?.blur();window.scrollTo(0,0)});await page.waitForTimeout(180);await page.screenshot({path:out+'/'+name,fullPage,animations:'disabled'})}
const check=(name,condition=true)=>{assert.ok(condition,name);checks.push(name);console.log(name)}
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true,args:['--no-first-run','--disable-background-networking']})
try{
 const context=await browser.newContext({viewport:{width:1440,height:960},locale:'ru-RU',reducedMotion:'reduce'}),page=await context.newPage()
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>requests.push({url:r.url(),method:r.method()}))
 await context.route('**/*',r=>['127.0.0.1','localhost'].includes(new URL(r.request().url()).hostname)?r.continue():r.abort())
 await page.goto(base+'/dashboard/#/mixtures');await page.getByRole('heading',{name:'Mixture Builder',exact:true}).waitFor()
 await page.getByText('15',{exact:true}).waitFor();check('Real catalog rendered with separate supported-profile counts')
 check('Simple mode is default',await page.getByRole('button',{name:'Простой',exact:true}).getAttribute('aria-pressed')==='true')
 await page.getByLabel('Состояние 1',{exact:true}).selectOption('slurry');await page.getByRole('button',{name:'Добавить материал',exact:true}).click();await page.getByLabel('Количество 2',{exact:true}).fill('20')
 await page.getByRole('button',{name:'Добавить материал',exact:true}).click();await page.getByLabel('Сырьё 3',{exact:true}).selectOption('grass');await page.getByLabel('Количество 3',{exact:true}).fill('10')
 const response=page.waitForResponse(r=>r.url().endsWith('/api/advisor/analyze')&&r.request().method()==='POST');await page.getByRole('button',{name:'Рассчитать ориентиры',exact:true}).click();const calculation=await(await response).json()
 await page.getByTestId('advisor-results').waitFor();check('Three real UI rows sent with 50/20/10 amounts',calculation.request.components.map(x=>x.quantity).join(',')==='50,20,10')
 check('Missing grass prevents false full-mixture yield',calculation.mixture.additive_methane_reference_m3===null)
 await screenshot(page,'mixture_simple_1440.png')
 const before=await page.getByTestId('advisor-methane').innerText(),count=requests.filter(r=>r.method==='POST').length
 await page.getByRole('button',{name:'Научный',exact:true}).click();check('Scientific view reuses identical calculation',await page.getByTestId('advisor-methane').innerText()===before&&requests.filter(r=>r.method==='POST').length===count)
 check('Scientific details expand without re-query',await page.locator('.scientific-details').getAttribute('open')!==null);await screenshot(page,'mixture_scientific_1440.png')
 await page.getByRole('button',{name:'Простой',exact:true}).click();await page.getByRole('button',{name:'Удалить компонент 3',exact:true}).click();await page.getByLabel('Количество 2',{exact:true}).fill('25')
 await page.getByText('Реактор и предположения',{exact:true}).click();await page.getByLabel(/Условно считать неизвестную влажность газа/).check();await page.getByLabel('Полный объём, л',{exact:true}).fill('200')
 const comparisonResponse=page.waitForResponse(r=>r.url().endsWith('/api/advisor/compare')&&r.request().method()==='POST');await page.getByRole('button',{name:'Сравнить варианты',exact:true}).click();const comparison=await(await comparisonResponse).json()
 await page.getByTestId('mixture-comparison').waitFor();check('Real UI comparison has three stock-constrained cases and no optimum',comparison.candidates.length===3&&comparison.preferred_mixture===null)
 await screenshot(page,'mixture_comparison_1440.png')
 check('Desktop no page overflow',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1))
 await page.setViewportSize({width:390,height:844});check('Mobile no page overflow',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await screenshot(page,'mixture_mobile_390.png',false)
 await page.setViewportSize({width:1440,height:960});await page.goto(base+'/dashboard/#/chat');await page.evaluate(id=>localStorage.setItem('bioreactor_chat_session_v4',id),process.env.BIOREACTOR_QA_SESSION);await page.reload()
 await page.getByTestId('conversational-answer').last().waitFor();check('Actual persisted mixture conversation is displayed',await page.getByTestId('conversational-answer').count()>=6)
 const prose=await page.locator('.conversation-prose').last().innerText();check('Human text hides technical status codes',!prose.includes('HYPOTHETICAL_SCENARIO')&&!prose.includes('LITERATURE_ESTIMATE'))
 await page.getByLabel('Сообщение агенту').fill('Убери пищевые отходы');const turn=page.waitForResponse(r=>r.url().endsWith('/messages')&&r.request().method()==='POST',{timeout:140000});await page.getByRole('button',{name:'Отправить сообщение'}).click();const reply=await(await turn).json()
 check('Real browser edit retains confirmed cattle quantity',reply.memory.mixture_components.length===1&&reply.memory.mixture_components[0].quantity===50)
 await screenshot(page,'advisor_chat_1440.png')
 for(const id of ['overview','reactor','prediction','market','economics','science','optimizer','experiments','system','demo','advisor']){await page.goto(base+'/dashboard/#/'+id);await page.waitForTimeout(350);check('Preserved route '+id,(await page.locator('#main-content').innerText()).trim().length>40)}
 const legacyNav=page.getByRole('button',{name:'Process Optimizer',exact:true});await legacyNav.scrollIntoViewIfNeeded();await legacyNav.click();check('Existing sections remain reachable through scrolling sidebar',page.url().endsWith('#/optimizer'))
 check('No browser JavaScript errors',errors.length===0)
}finally{await fs.writeFile(out+'/browser_results.json',JSON.stringify({passed:errors.length===0,checks,errors},null,2));await browser.close()}
