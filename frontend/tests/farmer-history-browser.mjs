// Display/restore of a genuine, completed Qwen QA conversation. No inference.
import { chromium } from 'playwright-core'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
let tracePath=process.env.BIOREACTOR_FARMER_TRACE??'../reports/qwen4b_manual_qa/limited_chat_1794471880875053300.json'
let trace=JSON.parse(await fs.readFile(tracePath,'utf8'))
const restoreNoModel=process.argv.includes('--restore-no-model')
if(process.argv.includes('--restore-live')||restoreNoModel){
 tracePath='../reports/farmer_consultant_20261112/browser_live_result.json'
 const saved=JSON.parse(await fs.readFile(tracePath,'utf8'))
 trace={status:saved.result.status,provider_calls:saved.result.reply.technical_metadata.experimental_qwen4b.provider_calls,session_id:saved.job.conversation_id,result:saved.result}
}
const followupFile=process.argv.find(x=>x.startsWith('--followup-message-file='))?.split('=').slice(1).join('=')
const liveFile=followupFile??process.argv.find(x=>x.startsWith('--live-message-file='))?.split('=').slice(1).join('=')
const liveOnly=process.argv.includes('--live-only')
assert.equal(trace.status,'COMPLETED')
if(restoreNoModel){
 assert.equal(trace.result.reply.technical_metadata.experimental_qwen4b.status,'blocked')
 assert.equal(trace.provider_calls.length,0)
}else assert.ok(trace.provider_calls.some(c=>c.metrics?.some(m=>m.generation_received)))
const base=process.env.BIOREACTOR_DEMO_URL??'http://127.0.0.1:8770'
const out='../reports/farmer_consultant_20261112';await fs.mkdir(out,{recursive:true})
const record={scope:'RESTORE_REAL_QWEN_HISTORY_ONLY_NOT_NEW_BROWSER_INFERENCE',trace:tracePath,checks:[],errors:[],requests:[]}
if(restoreNoModel)record.scope='RESTORE_ACTUAL_RESOURCE_BLOCKED_REPLY_NO_MODEL_INFERENCE'
const check=(name,passed)=>{assert.ok(passed,name);record.checks.push(name)}
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true,args:['--no-first-run','--disable-background-networking']})
try{
 const page=await browser.newPage({viewport:{width:1440,height:1000},locale:'ru-RU'})
 page.on('pageerror',e=>record.errors.push(e.message))
 page.on('request',r=>{if(r.url().includes('/api/'))record.requests.push({url:r.url(),method:r.method()})})
 if(!liveOnly)await page.addInitScript(id=>{if(!localStorage.getItem('bioreactor_chat_session_v4'))localStorage.setItem('bioreactor_chat_session_v4',id)},trace.session_id)
 await page.goto(base+'/dashboard/#/chat')
 const normalized=s=>s.replace(/\s+/g,' ').trim()
 if(!liveOnly){
 const answer=page.getByTestId('conversational-answer').last();await answer.waitFor()
 const expected=trace.result.reply.user_facing_answer
 const validate=async()=>{
  const prose=normalized(await answer.locator('.conversation-prose').innerText())
  for(const s of expected.sections)check('Persisted section: '+s.title,prose.includes(normalized(s.body)))
  check('Farm mode badge visible',await answer.getByText('Консультация для хозяйства',{exact:true}).isVisible())
  check('Methane and input units preserved',prose.includes('л CH₄')&&prose.includes('16.31 г/л'))
  check('Working capacity still unknown',prose.includes('Номинальная вместимость не равна рабочему объёму'))
  check('No private evidence IDs in normal prose',!/(?:s\d+\.methane|profile_ids|chae2008-swine|B_heat)/.test(prose))
  check('At most one clarification, matching persisted reply',(await answer.locator('.clarification-card').count())===(expected.question?1:0))
  check('Primary source link present',await answer.locator('a[href="https://doi.org/10.1016/j.biortech.2006.11.063"]').count()>0)
 }
 await validate();await page.screenshot({path:out+'/chat_history_desktop.png',fullPage:true})
 await page.reload();await answer.waitFor();await validate();check('Session survives reload',await page.evaluate(()=>localStorage.getItem('bioreactor_chat_session_v4'))===trace.session_id)
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:out+'/chat_history_mobile.png',fullPage:true})
 check('No horizontal mobile overflow',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1))
 check('No new chat jobs or model requests',!record.requests.some(r=>r.method==='POST'&&/\/(?:jobs|messages)$/.test(new URL(r.url).pathname)))
 }
 if(liveFile){
  record.scope='REAL_BROWSER_CHAT_WITH_EXISTING_GUARDED_QWEN4B_PROVIDER'
  const bytes=await fs.readFile(liveFile);const decoded=new TextDecoder('utf-8',{fatal:true}).decode(bytes)
  assert.ok(Buffer.from(decoded,'utf8').equals(bytes),'UTF-8 round trip')
  const question=decoded.trim();assert.ok(question&&question.length<=12000)
  const capability=await(await page.request.get(base+'/api/dashboard/status')).json()
  assert.equal(capability.experimental_chat?.enabled,true)
  await page.setViewportSize({width:1440,height:1000})
  if(!followupFile)await page.getByRole('button',{name:'Новый диалог',exact:true}).click()
  await page.getByTestId('chat-input').fill(question)
  const accepted=page.waitForResponse(r=>r.request().method()==='POST'&&/\/chat\/sessions\/[^/]+\/jobs$/.test(new URL(r.url()).pathname))
  await page.getByTestId('send-chat').click();const job=await(await accepted).json()
  let result;const deadline=Date.now()+135000
  while(Date.now()<deadline){
   result=await(await page.request.get(base+job.result_reference)).json()
   if(result.terminal)break
   await page.waitForTimeout(200)
  }
  if(!result?.terminal)await page.request.post(base+'/api/dashboard/jobs/'+job.id+'/cancel')
  const live={scope:record.scope,question_origin:'AGENT_AUTHORED_VALIDATION_NOT_FARMER_TRAFFIC',question,job,result,continues_saved_session:followupFile?trace.session_id:null}
  await fs.writeFile(out+'/browser_live_result.json',JSON.stringify(live,null,2))
  record.live={status:result?.status,job:job.id,artifact:out+'/browser_live_result.json'}
  check('Live browser job completed',result?.status==='COMPLETED')
  const reply=result.reply;const guard=reply.technical_metadata?.experimental_qwen4b
  check('Real 4B generation received',guard?.provider_calls.some(c=>c.model==='qwen3:4b-q4_K_M'&&c.metrics?.some(m=>m.generation_received)))
  check('Accepted model explanation, not fallback',reply.technical_metadata.final_author.startsWith('qwen_'))
  check('Scientific verifier ran',reply.technical_metadata.scientific_answer_verification.checked===true&&reply.technical_metadata.scientific_answer_verification.status==='passed')
  check('Target model unloaded',guard.unload?.status==='UNLOADED'&&guard.after?.running_models?.length===0)
  await page.waitForFunction(()=>Boolean(document.querySelector('[data-testid="conversational-answer"]')))
  const displayed=page.getByTestId('conversational-answer').last()
  await displayed.getByText('Консультация для хозяйства',{exact:true}).waitFor()
  for(const section of reply.user_facing_answer.sections)check('Live section delivered: '+section.title,normalized(await displayed.locator('.conversation-prose').innerText()).includes(normalized(section.body)))
  await page.screenshot({path:out+'/browser_live.png',fullPage:true})
  await page.reload();await displayed.waitFor()
  await displayed.getByText('Консультация для хозяйства',{exact:true}).waitFor()
  check('New live answer survives reload',normalized(await displayed.innerText()).includes(normalized(reply.user_facing_answer.sections[0].body)))
 }
 check('No browser JS errors',record.errors.length===0)
 record.status='PASSED';console.log(JSON.stringify({status:record.status,checks:record.checks.length,scope:record.scope}))
}catch(e){record.status='FAILED';record.error=String(e);throw e}
finally{await fs.writeFile(out+(restoreNoModel?'/browser_blocked_followup.json':'/browser_history.json'),JSON.stringify(record,null,2));await browser.close()}
