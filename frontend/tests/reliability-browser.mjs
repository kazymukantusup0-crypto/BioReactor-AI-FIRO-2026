// P0 real Chrome + HTTP + SQLite. Normal questions use real no_llm scientific tools.
// Network faults are injected explicitly. TEST_P0_* requests only exercise lifecycle.
import { chromium } from 'playwright-core'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import path from 'node:path'

const base=process.env.BIOREACTOR_QA_URL??'http://127.0.0.1:8772'
const output=path.resolve('../reports/reliability')
await fs.mkdir(output,{recursive:true})
const label='p0_browser_'+new Date().toISOString().replace(/[:.]/g,'-')
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true,args:['--disable-gpu','--no-first-run']})
const context=await browser.newContext({viewport:{width:1440,height:1000},locale:'ru-RU'})
const page=await context.newPage();const checks=[];const errors=[];const jobs=[]
page.on('pageerror',error=>errors.push(String(error)))
const check=(name,value)=>{checks.push({name,passed:Boolean(value)});assert.ok(value,name)}
const get=async url=>{const response=await context.request.get(base+url);assert.equal(response.status(),200);return response.json()}
const create=async()=>{const response=await context.request.post(base+'/api/dashboard/chat/sessions',{data:{mode:'no_llm',context:{},conversation_version:'7'}});assert.equal(response.status(),201);return response.json()}
const ready=async()=>{await page.getByTestId('chat-input').waitFor();await page.waitForFunction(()=>!document.querySelector('[data-testid="chat-input"]').disabled&&!document.querySelector('.chat-header select').disabled)}
const readResult=async job=>{
  await page.locator(`[data-request-id="${job.request_id}"] [data-testid="chat-result"]`).waitFor({timeout:60000})
  const result=await get(job.result_reference);check('Saved result '+job.request_id,Boolean(result.reply));return result.reply
}
const send=async text=>{
  await ready();await page.getByTestId('chat-input').fill(text)
  const response=page.waitForResponse(r=>r.url().endsWith('/jobs')&&r.request().method()==='POST')
  await page.getByTestId('send-chat').click()
  const job=await (await response).json();jobs.push(job)
  return {job,reply:await readResult(job)}
}
let session
try {
  session=await create()
  await context.addInitScript(id=>{if(!localStorage.getItem('bioreactor_chat_session_v4'))localStorage.setItem('bioreactor_chat_session_v4',id)},session.id)
  await page.goto(base+'/dashboard/#/chat');await ready()
  // Keep one accepted POST reply in flight, then reload the actual browser.
  let release;let accepted
  const gate=new Promise(resolve=>{release=resolve})
  const acceptedJob=new Promise(resolve=>{accepted=resolve})
  const postPattern='**/api/dashboard/chat/sessions/*/jobs'
  const hold=async route=>{
    if(route.request().method()!=='POST')return route.continue()
    const response=await route.fetch();accepted(await response.json());await gate
    try{await route.fulfill({response})}catch{/* Reload deliberately aborted this response. */}
  }
  await context.route(postPattern,hold)
  const a='Привет, у меня есть 478 литров жидкого коровьего навоза и реактор вместимостью 700 литров. Мне лучше продать навоз или переработать и какую температуру ставить?'
  await page.getByTestId('chat-input').fill(a);await page.getByTestId('send-chat').click()
  const first=await acceptedJob;jobs.push(first)
  check('Outbox retains accepted request before POST reply',await page.evaluate(id=>JSON.parse(localStorage.getItem('bioreactor-pending-delivery:'+id)).requestId,session.id)===first.request_id)
  await page.reload();release();await context.unroute(postPattern,hold)
  const aReply=await readResult(first);await ready()
  check('Reload retains one turn',await page.locator(`[data-request-id="${first.request_id}"]`).count()===1)
  check('Reload does not execute twice',(await get('/api/dashboard/jobs/'+first.id)).attempt_count===1)
  check('Actual tools receive batch A',aReply.memory.facts.quantity.value===478&&aReply.memory.facts.reactor_total_volume_l.value===700)
  await page.screenshot({path:path.join(output,label+'_reload.png'),fullPage:true})

  // A failed acknowledgement must not hide the following real calculation.
  const ackPattern='**/api/dashboard/jobs/*/ack'
  await context.route(ackPattern,route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'TEST_P0 injected acknowledgement outage'})}))
  const b=await send(a.replace('478','47').replace('700','114'))
  check('Batch B replaces A without false conflict',b.reply.memory.facts.quantity.value===47&&b.reply.memory.facts.reactor_total_volume_l.value===114&&!b.reply.error_type)
  check('Batch A archived',b.reply.memory.task_history.at(-1).facts.quantity.value===478)
  await ready();check('Ack failure leaves answer visible',await page.locator(`[data-request-id="${b.job.request_id}"] [data-testid="chat-result"]`).isVisible())
  await context.unroute(ackPattern)
  const c=await send('У меня 470 л свежей травы и реактор 840 л. Стоит ли производить биогаз?')
  check('Grass is a new batch C',c.reply.memory.facts.material.value==='grass'&&c.reply.memory.facts.quantity.value===470&&c.reply.memory.facts.reactor_total_volume_l.value===840&&!c.reply.error_type)
  check('Batch B archived',c.reply.memory.task_history.at(-1).facts.quantity.value===47)
  const corrected=await send('исправь: 450 литров и 800 литров')
  check('Correction keeps task identity',corrected.reply.memory.task_id===c.reply.memory.task_id)
  check('Correction changes both bound parameters',corrected.reply.memory.facts.quantity.value===450&&corrected.reply.memory.facts.reactor_total_volume_l.value===800)
  const conditional=await send('а если реактор 900 литров?')
  check('Hypothetical reactor does not replace measurement',conditional.reply.memory.facts.reactor_total_volume_l.value===800&&conditional.reply.memory.assumptions.reactor_total_volume_l.value===900)
  const conflict=await send('У меня одновременно 47 и 478 литров одной и той же партии')
  check('True conflict remains explicit',conflict.reply.error_type==='ConflictingValuesInSameRequest'&&conflict.reply.memory.facts.quantity.value===450)
  await ready()
  await page.evaluate(id=>localStorage.setItem('bioreactor-pending-delivery:'+id,'{TEST corrupt JSON'),session.id)
  await page.reload();await ready()
  check('Corrupt outbox leaves history visible',(await page.getByTestId('chat-result').count())===6)
  check('Corrupt input remains archived',await page.evaluate(id=>Object.keys(localStorage).some(k=>k.startsWith('bioreactor-pending-delivery:'+id+':rejected:')),session.id))
  await page.screenshot({path:path.join(output,label+'_batches.png'),fullPage:true})

  // Separate conversation: explicitly labelled test execution gates, no scientific answer.
  const faultSession=await create()
  await page.evaluate(id=>{localStorage.setItem('bioreactor_chat_session_v4',id);window.dispatchEvent(new StorageEvent('storage',{key:'bioreactor_chat_session_v4',newValue:id}))},faultSession.id)
  await ready();await page.getByTestId('chat-input').fill('TEST_P0_CANCEL execution fixture')
  let response=page.waitForResponse(r=>r.url().endsWith('/jobs')&&r.request().method()==='POST')
  await page.getByTestId('send-chat').click();const cancelled=await (await response).json();jobs.push(cancelled)
  await page.getByTestId('cancel-job').click();await page.getByTestId('job-terminal').waitFor({timeout:15000});await ready()
  check('Running cancellation displays terminal state',(await get('/api/dashboard/jobs/'+cancelled.id)).status==='CANCELLED')
  check('Cancelled gate cannot change scientific state',(await get('/api/dashboard/chat/sessions/'+faultSession.id)).state_version===0)
  await page.getByTestId('chat-input').fill('TEST_P0_TIMEOUT execution fixture')
  response=page.waitForResponse(r=>r.url().endsWith('/jobs')&&r.request().method()==='POST')
  await page.getByTestId('send-chat').click();const timed=await (await response).json();jobs.push(timed)
  await page.locator(`[data-request-id="${timed.request_id}"] [data-testid="job-terminal"]`).waitFor({timeout:15000});await ready()
  check('Timeout displays terminal state',(await get('/api/dashboard/jobs/'+timed.id)).status==='TIMED_OUT')
  await page.reload();await ready()
  check('Reload retains cancellation and timeout',(await page.getByTestId('job-terminal').count())===2)
  await page.screenshot({path:path.join(output,label+'_terminal.png'),fullPage:true})
  check('No browser exceptions',errors.length===0)
  const states=await Promise.all(jobs.map(j=>get('/api/dashboard/jobs/'+j.id)))
  await fs.writeFile(path.join(output,label+'.json'),JSON.stringify({checks,errors,session:session.id,jobs:states,browser:browser.version(),qwen:'NOT RUN: P0 no_llm and explicit lifecycle fixtures',base},null,2))
  console.log(JSON.stringify({artifact:path.join(output,label+'.json'),checks,errors}))
}catch(error){
  await page.screenshot({path:path.join(output,label+'_failure.png'),fullPage:true})
  await fs.writeFile(path.join(output,label+'_failure.json'),JSON.stringify({checks,errors,session:session?.id,jobs,error:String(error)},null,2));throw error
}finally{await browser.close()}
