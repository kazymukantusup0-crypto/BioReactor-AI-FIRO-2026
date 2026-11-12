import {chromium} from 'playwright-core'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
const base=process.env.BIOREACTOR_DEMO_URL??'http://127.0.0.1:8770'
const out=process.env.BIOREACTOR_DEMO_OUT??'../reports/firo_demo_mvp';await fs.mkdir(out,{recursive:true})
const selected=process.argv.find(x=>x.startsWith('--live-case='))?.split('=')[1]
if(selected)assert.ok(['A','B','C'].includes(selected))
const record={base,started:new Date().toISOString(),checks:[],live:[],errors:[]}
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true,args:['--no-first-run','--disable-background-networking']})
const check=(name,value)=>{assert.ok(value,name);record.checks.push(name)}
try{
 const page=await browser.newPage({viewport:{width:1440,height:1000},locale:'ru-RU'})
 page.on('pageerror',error=>record.errors.push(error.message))
 await page.goto(base+'/dashboard/#/demo')
 await page.getByRole('heading',{name:'FIRO Demo MVP',exact:true}).waitFor()
 check('Three real scenario buttons',await page.getByRole('button',{name:/^Запустить [ABC]$/}).count()===3)
 const run=async(letter)=>{
  const response=page.waitForResponse(r=>r.url().endsWith('/api/dashboard/firo-demo/runs')&&r.request().method()==='POST')
  await page.getByRole('button',{name:'Запустить '+letter,exact:true}).click()
  const data=await(await response).json()
  await page.getByTestId('firo-answer').waitFor();return data
 }
 for(const letter of ['A','B','C']){
  const data=await run(letter)
  check(letter+' works without requesting a model',data.explanation.status==='not_requested')
  const text=await page.getByTestId('firo-result').innerText()
  if(letter==='A'){check('Python returns 150 L methane',data.results[0].value===150&&text.includes('150 л CH₄'));check('Calculated not measured',text.includes('Рассчитано')&&data.results[0].provenance==='CALCULATED')}
  if(letter==='B'){check('Literature potential is separate from unknown timed yield',data.results[1].value===null&&data.estimate.estimation_mode==='LITERATURE_ESTIMATE'&&text.includes('2922')&&text.includes('Литературная оценка'));check('Nominal volume is not working volume',data.verification.capacity.reactor_working_volume_l===null&&data.verification.capacity.simultaneous_load_possible===null)}
  if(letter==='C')check('Oxygen and diverse pathways from sources',data.answer.includes('без свободного кислорода')&&data.answer.includes('CO₂')&&data.answer.includes('Не все виды'))
  await page.screenshot({path:out+'/offline_'+letter+'.png',fullPage:true})
  const id=data.id;await page.reload();await page.getByTestId('firo-answer').waitFor()
  check(letter+' restored after reload',await page.evaluate(()=>localStorage.getItem('bioreactor-firo-mvp-run'))===id&&(await page.getByTestId('firo-answer').innerText()).includes(data.answer.slice(0,40)))
 }
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:out+'/mobile.png',fullPage:true})
 check('No mobile horizontal overflow',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1))
 await page.setViewportSize({width:1440,height:1000})
 if(process.argv.includes('--with-qwen')){
  for(const letter of selected?[selected]:['A','B','C']){
   const before=await run(letter)
   const response=page.waitForResponse(r=>r.url().endsWith('/explain')&&r.request().method()==='POST',{timeout:75000})
   await page.getByRole('button',{name:'Получить пояснение Qwen3 4B',exact:true}).click()
   const r=await response;assert.equal(r.status(),200);const data=await r.json()
   await fs.writeFile(out+'/qwen_'+letter+'.json',JSON.stringify(data,null,2))
   record.live.push({case:letter,status:data.explanation.status,telemetry:data.explanation.telemetry})
   check(letter+' preserves verified Python result with model',JSON.stringify(data.results)===JSON.stringify(before.results)&&data.answer===before.answer)
   if(data.explanation.status==='accepted'){
    await page.getByTestId('firo-model-answer').waitFor()
    check(letter+' accepted explanation displayed',(await page.getByTestId('firo-model-answer').innerText())===data.explanation.text)
   }else{check(letter+' clear model status',Boolean(data.explanation.message)&&data.explanation.text===null)}
   await page.screenshot({path:out+'/qwen_'+letter+'.png',fullPage:true})
   const telemetry=data.explanation.telemetry
   if(data.explanation.status==='blocked'||telemetry?.stop_reason||telemetry?.unload&&!['UNLOADED','ALREADY_EMPTY'].includes(telemetry.unload.status))break
  }
 }
 check('No browser JS errors',record.errors.length===0)
 record.status='PASSED';console.log(JSON.stringify({status:record.status,checks:record.checks,live:record.live.map(x=>({case:x.case,status:x.status}))}))
}catch(error){record.status='FAILED';record.error=String(error);throw error}
finally{record.finished=new Date().toISOString();await fs.writeFile(out+(selected?'/browser_'+selected+'.json':'/browser.json'),JSON.stringify(record,null,2));await browser.close()}
