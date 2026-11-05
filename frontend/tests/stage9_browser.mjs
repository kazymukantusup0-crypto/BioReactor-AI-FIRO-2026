// Real HTTP/server/Qwen; no intercepted routes or synthetic model replies.
import { chromium } from 'playwright-core'
import fs from 'node:fs/promises'
import path from 'node:path'
import assert from 'node:assert/strict'
const output=path.resolve('../reports/stage9')
await fs.mkdir(output,{recursive:true})
const base='http://127.0.0.1:8770'
const crash=process.env.STAGE9_CRASH_TEST==='1'
const artifact=crash?'backend_crash':'browser'
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true,args:['--disable-gpu']})
const context=await browser.newContext({viewport:{width:1440,height:1000}})
const page=await context.newPage();const errors=[];const checks=[]
page.on('pageerror',e=>errors.push(String(e)))
const check=(name,value)=>{checks.push({name,passed:Boolean(value)});assert.ok(value,name)}
try {
  const response=await context.request.post(base+'/api/dashboard/chat/sessions',{data:{mode:'offline',context:{},conversation_version:'7'}})
  const session=await response.json()
  await context.addInitScript(id=>localStorage.setItem('bioreactor_chat_session_v4',id),session.id)
  await page.goto(base+'/dashboard/#/chat');await page.getByTestId('chat-input').waitFor()
  await page.getByTestId('chat-input').fill('Есть 4 кг пищевых отходов и реактор 70 литров. Сколько метана и какова ценность энергии?')
  const submitted=page.waitForResponse(r=>r.url().endsWith('/jobs')&&r.request().method()==='POST')
  await page.getByTestId('send-chat').click();const job=await (await submitted).json()
  check('Short submit returns persisted job',job.id&&job.request_id)
  await page.getByTestId('job-progress').waitFor()
  await page.reload();await page.getByTestId('job-progress').waitFor()
  check('Reload restores same request automatically',await page.locator(`[data-request-id="${job.request_id}"]`).count()===1)
  if(crash) {
    await page.waitForFunction(async id=>{const j=await (await fetch('/api/dashboard/jobs/'+id)).json();return j.current_stage==='understanding'},job.id,{timeout:60000})
    await fs.writeFile(path.join(output,'crash_ready.json'),JSON.stringify({session:session.id,job}))
  }
  await page.getByTestId('chat-result').waitFor({timeout:1800000})
  let result=await (await context.request.get(base+job.result_reference)).json()
  for(let i=0;!result.terminal&&i<30;i++){await page.waitForTimeout(200);result=await (await context.request.get(base+job.result_reference)).json()}
  const reply=result.reply
  if(crash) {
    const recovered=await (await context.request.get(base+'/api/dashboard/jobs/'+job.id)).json()
    check('Backend crash retries persisted job',recovered.attempt_count>=2)
    const events=await (await context.request.get(base+'/api/dashboard/jobs/'+job.id+'/events')).json()
    check('Recovery is present in durable event history',events.events.some(e=>e.details.reason==='stale_heartbeat'))
  }
  check('Real Qwen participates',reply.provider_status.some(p=>p.model==='qwen3:8b'&&p.actual_generation))
  check('Numeric tool output reaches real chat',await page.getByTestId('chat-result').innerText().then(t=>t.includes('м³')))
  check('No duplicate turn after reload',await page.locator(`[data-request-id="${job.request_id}"]`).count()===1)
  await page.screenshot({path:path.join(output,'chat_restored.png'),fullPage:true})
  check('Calculator transfer enabled after result',await page.getByTestId('open-calculator').isEnabled())
  await page.getByTestId('open-calculator').click()
  await page.getByTestId('quantity-0').waitFor()
  check('Calculator retains exact mass',await page.getByTestId('quantity-0').inputValue()==='4')
  check('Calculator retains vessel capacity',await page.getByTestId('reactor-total').inputValue()==='70')
  for(const route of ['overview','market','reactor','science','system']) {
    await page.goto(base+'/dashboard/#/'+route);await page.locator('h1').waitFor();check('Route '+route,await page.locator('h1').innerText().then(Boolean))
  }
  check('No browser exceptions',errors.length===0)
  await fs.writeFile(path.join(output,artifact+'_live.json'),JSON.stringify({checks,errors,session:session.id,job,reply,browser:browser.version()},null,2))
  console.log(JSON.stringify({checks,errors}))
} catch(e) {
  await page.screenshot({path:path.join(output,'browser_failure.png'),fullPage:true})
  await fs.writeFile(path.join(output,'browser_failure.json'),JSON.stringify({checks,errors,error:String(e)},null,2));throw e
} finally {await browser.close()}
