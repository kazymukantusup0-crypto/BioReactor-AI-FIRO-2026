// Real process-crash QA. The driver kills/restarts ONLY its isolated 8772 server.
import { chromium } from 'playwright-core'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import path from 'node:path'
const output=path.resolve('../reports/reliability')
const base='http://127.0.0.1:8772'
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true,args:['--disable-gpu']})
const context=await browser.newContext();const page=await context.newPage();const errors=[]
page.on('pageerror',e=>errors.push(String(e)))
let job;let session
try {
  session=await (await context.request.post(base+'/api/dashboard/chat/sessions',{data:{mode:'no_llm',context:{},conversation_version:'7'}})).json()
  await context.addInitScript(id=>localStorage.setItem('bioreactor_chat_session_v4',id),session.id)
  await page.goto(base+'/dashboard/#/chat')
  await page.waitForFunction(()=>document.querySelector('.chat-header select')&&!document.querySelector('.chat-header select').disabled)
  await page.getByTestId('chat-input').fill('TEST_P0_CRASH У меня 5 кг пищевых отходов и реактор 90 литров. Сколько метана?')
  const submitted=page.waitForResponse(r=>r.url().endsWith('/jobs')&&r.request().method()==='POST')
  await page.getByTestId('send-chat').click();job=await (await submitted).json()
  await page.waitForFunction(async id=>(await (await fetch('/api/dashboard/jobs/'+id)).json()).current_stage==='understanding',job.id)
  await fs.writeFile(path.join(output,'crash_ready.json'),JSON.stringify({session:session.id,job}))
  await page.locator(`[data-request-id="${job.request_id}"] [data-testid="chat-result"]`).waitFor({timeout:120000})
  const snapshot=await (await context.request.get(base+'/api/dashboard/chat/sessions/'+session.id)).json()
  const done=snapshot.jobs.find(j=>j.id===job.id)
  assert.equal(done.status,'COMPLETED');assert.equal(done.attempt_count,2)
  assert.equal(snapshot.state_version,1);assert.equal(snapshot.turns.length,1)
  assert.equal(snapshot.turns[0].reply.memory.facts.quantity.value,5)
  assert.equal(snapshot.turns[0].reply.memory.facts.unit.value,'kg')
  await page.reload();await page.getByTestId('chat-result').waitFor()
  assert.equal(await page.getByTestId('chat-result').count(),1);assert.equal(errors.length,0)
  const events=await (await context.request.get(base+'/api/dashboard/jobs/'+job.id+'/events')).json()
  assert.ok(events.events.some(e=>e.details.reason==='stale_heartbeat'))
  await page.screenshot({path:path.join(output,'p0_process_crash_restored.png'),fullPage:true})
  await fs.writeFile(path.join(output,'p0_process_crash.json'),JSON.stringify({passed:true,snapshot,events,errors,browser:browser.version(),qwen:'NOT RUN'},null,2))
  console.log(JSON.stringify({passed:true,session:session.id,job:job.id,attempts:done.attempt_count,state_version:snapshot.state_version,turns:snapshot.turns.length}))
}catch(error){await fs.writeFile(path.join(output,'p0_process_crash_failure.json'),JSON.stringify({error:String(error),errors,job,session}));throw error}
finally{await browser.close()}
