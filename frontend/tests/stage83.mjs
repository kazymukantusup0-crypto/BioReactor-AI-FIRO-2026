// Installed Chrome + real local FastAPI. No mocked API responses.
import { chromium } from 'playwright-core'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
const base=process.env.STAGE83_URL??'http://127.0.0.1:8767'
const out='../reports/stage8_3'
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true})
const page=await browser.newPage({viewport:{width:1440,height:1000},locale:'ru-RU'})
const errors=[],checks=[],requests=[]
page.on('pageerror',e=>errors.push(e.message))
page.on('response',r=>{if(r.url().endsWith('/api/advisor/analyze'))requests.push(r.status())})
const nextCalculation=()=>page.waitForResponse(r=>r.url().endsWith('/api/advisor/analyze')&&r.request().method()==='POST'&&r.status()===200,{timeout:60000})
try {
 await page.goto(base+'/dashboard/#/substrates')
 await page.getByLabel('Сырьё 1',{exact:true}).waitFor()
 let wait=nextCalculation()
 await page.getByLabel('Сырьё 1',{exact:true}).selectOption('food_waste')
 await page.getByLabel('Количество 1',{exact:true}).fill('5')
 let response=await wait, result=await response.json()
 // A response in flight may belong to the initial inventory; wait for exact requested inputs.
 while(result.original_request.components[0].material!=='food_waste'||result.original_request.components[0].quantity!==5){response=await nextCalculation();result=await response.json()}
 assert.ok(Math.abs(result.mixture.additive_methane_reference_m3.low-(5*.1206*527.5/1000*273.2/273.15))<1e-9)
 await page.getByTestId('advisor-methane').filter({hasText:'0,32'}).waitFor()
 checks.push('Automatic calculation uses actual API food profile')
 const direct=await (await page.request.post(base+'/api/advisor/analyze',{data:result.original_request})).json()
 assert.deepEqual(result.mixture,direct.mixture);checks.push('Browser and direct API produce identical mixture values')
 await page.getByText('Реактор и предположения',{exact:true}).click()
 await page.getByLabel('Полный объём, л',{exact:true}).fill('90')
 await page.getByLabel('Подтверждённый рабочий объём, л',{exact:true}).fill('70')
 await page.getByLabel('Инокулюм, л',{exact:true}).fill('10')
 await page.getByLabel('Режим загрузки',{exact:true}).selectOption('batch')
 await page.getByText('Загрузка, энергия и затраты партии',{exact:true}).click()
 wait=nextCalculation();await page.getByLabel('Добавленная вода, л',{exact:true}).fill('10')
 result=await (await wait).json()
 while(result.original_request.decision.reactor.dilution_water_l!==10)result=await (await nextCalculation()).json()
 assert.ok(Math.abs(result.mixture.additive_methane_reference_m3.low-(5*.1206*527.5/1000*273.2/273.15))<1e-9)
 assert.ok(Math.abs(result.engineering.feed_plus_water_ts_fraction.low-5*.1264/15)<1e-12)
 checks.push('Changing water recalculates dilution without increasing methane')
 wait=nextCalculation();await page.getByLabel('Подготовка, KZT/партию',{exact:true}).fill('100')
 result=await (await wait).json()
 while(result.original_request.decision.costs.preparation?.low!==100)result=await (await nextCalculation()).json()
 assert.equal(result.decision_analysis.operating_costs.known_subtotal.low,100)
 assert.equal(result.decision_analysis.operating_costs.complete_total,null)
 checks.push('Costs reactively reach economic module; unknown costs remain unknown')
 await page.screenshot({path:out+'/dashboard_food.png',fullPage:true})
 wait=nextCalculation();await page.getByLabel('Сырьё 1',{exact:true}).selectOption('grass');await page.getByLabel('Количество 1',{exact:true}).fill('58')
 result=await (await wait).json()
 while(result.original_request.components[0].material!=='grass'||result.original_request.components[0].quantity!==58)result=await (await nextCalculation()).json()
 assert.equal(result.scenario_count,6)
 await page.getByLabel('Научный сценарий',{exact:true}).selectOption('1')
 checks.push('Grass scenarios are separate selectable studies, not pooled endpoints')
 await page.screenshot({path:out+'/dashboard_grass.png',fullPage:true})
 await page.setViewportSize({width:390,height:844})
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1))
 checks.push('Mobile layout has no horizontal document overflow')
 await page.screenshot({path:out+'/dashboard_mobile.png',fullPage:true})
 assert.deepEqual(errors,[])
 await fs.writeFile(out+'/browser.json',JSON.stringify({status:'passed',checks,errors,requests},null,2))
 console.log(checks)
} catch(e) {
 await page.screenshot({path:out+'/browser_failure.png',fullPage:true})
 await fs.writeFile(out+'/browser.json',JSON.stringify({status:'failed',error:String(e),checks,errors,requests},null,2))
 throw e
} finally {await browser.close()}
