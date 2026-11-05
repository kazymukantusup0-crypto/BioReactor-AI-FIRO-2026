import {chromium} from 'playwright-core'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
assert.equal(process.env.BIOREACTOR_QA_ISOLATED,'1')
const base=process.env.BIOREACTOR_QA_URL,out='../reports/stage7_7',checks=[],errors=[];let completed=false
const check=(name,value=true)=>{assert.ok(value,name);checks.push(name);console.log(name)}
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true,args:['--no-first-run','--disable-background-networking']})
const shot=async(page,name,fullPage=true)=>{await page.evaluate(()=>{document.activeElement?.blur();window.scrollTo(0,0)});await page.waitForTimeout(120);await page.screenshot({path:out+'/'+name,fullPage,animations:'disabled'})}
try{
 const context=await browser.newContext({viewport:{width:1440,height:960},locale:'ru-RU',reducedMotion:'reduce'}),page=await context.newPage()
 page.on('pageerror',error=>errors.push(error.message))
 await context.route('**/*',r=>['127.0.0.1','localhost'].includes(new URL(r.request().url()).hostname)?r.continue():r.abort())
 await page.goto(base+'/dashboard/#/overview');await page.getByRole('heading',{name:'Что можно получить из вашего сырья?'}).waitFor()
 await page.getByText('Подключено',{exact:true}).waitFor();await page.locator('.home-market-row').first().waitFor()
 check('Home uses lightweight health and price requests',!(await page.locator('body').innerText()).includes('KZT/KZT'))
 const removed=['Лабораторный потенциал метана','Что выгоднее для вашей партии?','Process Optimizer','Experiment Lab']
 const removedCounts=await Promise.all(removed.map(t=>page.getByText(t,{exact:true}).count()));check('Removed headings absent from main interface',removedCounts.every(n=>n===0))
 check('One unified navigation entry',await page.getByRole('button',{name:'Сырьё и смеси',exact:true}).count()===1)
 await shot(page,'home_1440.png')
 for(const old of ['advisor','mixtures','prediction','economics','optimizer','experiments']){
  await page.goto(base+'/dashboard/#/'+old);await page.getByRole('heading',{name:'Сырьё и смеси',exact:true}).waitFor()
  check('Retained link '+old+' redirects',page.url().endsWith('#/substrates'))
 }
 await page.getByLabel('Количество 1',{exact:true}).fill('100');await page.getByLabel('Единицы 1',{exact:true}).selectOption('L');await page.getByLabel('Состояние 1',{exact:true}).selectOption('slurry')
 await page.getByRole('button',{name:'Добавить материал',exact:true}).click();await page.getByLabel('Количество 2',{exact:true}).fill('20')
 check('Single form with two components',await page.locator('form').count()===1&&await page.getByLabel('Сырьё 2',{exact:true}).count()===1)
 const calculated=page.waitForResponse(r=>r.url().endsWith('/api/advisor/analyze')&&r.request().method()==='POST');await page.getByRole('button',{name:'Получить оценку',exact:true}).click();const result=await(await calculated).json()
 check('Real calculation uses 100 L and 20 kg',result.request.components[0].quantity===100&&result.request.components[0].unit==='L'&&result.request.components[1].quantity===20)
 await page.getByTestId('advisor-methane').waitFor();check('Conditional methane shown from Python',/3[,.]/.test(await page.getByTestId('advisor-methane').innerText()))
 check('Detailed scientific cards closed in simple mode',await page.locator('.compact-science').getAttribute('open')===null)
 await shot(page,'substrates_1440.png')
 const before=await page.getByTestId('advisor-methane').innerText();await page.getByRole('button',{name:'Научный',exact:true}).click();check('Same result in scientific mode',await page.getByTestId('advisor-methane').innerText()===before)
 await page.getByRole('button',{name:'Простой',exact:true}).click();check('Returning to simple mode closes scientific cards',await page.locator('.compact-science').getAttribute('open')===null)
 const compared=page.waitForResponse(r=>r.url().endsWith('/api/advisor/compare')&&r.request().method()==='POST');await page.getByRole('button',{name:'Сравнить варианты',exact:true}).click();const comparison=await(await compared).json()
 check('Actual comparison retained',comparison.candidates.length===3&&comparison.preferred_mixture===null)
 await page.goto(base+'/dashboard/#/market');await page.goto(base+'/dashboard/#/substrates');await page.getByLabel('Количество 1',{exact:true}).waitFor();check('UI inventory survives page navigation',await page.getByLabel('Количество 1',{exact:true}).inputValue()==='100'&&await page.getByLabel('Единицы 1',{exact:true}).inputValue()==='L')
 await page.setViewportSize({width:390,height:844});check('No horizontal overflow on mobile',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await shot(page,'substrates_390.png',false)
 await page.setViewportSize({width:1440,height:960});await page.goto(base+'/dashboard/#/chat');await page.evaluate(id=>localStorage.setItem('bioreactor_chat_session_v4',id),process.env.BIOREACTOR_QA_SESSION);await page.reload()
 await page.getByTestId('conversational-answer').last().waitFor();check('Actual eight-turn dialogue visible',await page.getByTestId('conversational-answer').count()===8)
 check('One-sentence answer stays short',(await page.locator('.conversation-prose').last().innerText()).length<400)
 check('Scientific trace closed by default',await page.locator('.conversation-technical').last().getAttribute('open')===null)
 await page.getByLabel('Сообщение агенту').fill('Сколько газа?');const follow=page.waitForResponse(r=>r.url().endsWith('/messages')&&r.request().method()==='POST');await page.getByRole('button',{name:'Отправить сообщение',exact:true}).click();const reply=await(await follow).json()
 check('Browser follow-up remembers mixture',reply.memory.mixture_components.length===2&&reply.memory.mixture_components[0].quantity===142)
 check('Browser follow-up runs only gas tool',reply.tools.length===1&&reply.tools[0].tool==='estimate_substrate_gas')
 await shot(page,'smart_chat_1440.png')
 check('No browser JavaScript errors',errors.length===0)
 completed=true
}finally{await fs.writeFile(out+'/browser_results.json',JSON.stringify({passed:completed&&errors.length===0,checks,errors},null,2));await browser.close()}
