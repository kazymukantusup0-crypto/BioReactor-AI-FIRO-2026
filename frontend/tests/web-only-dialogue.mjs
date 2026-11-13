import {chromium} from 'playwright-core'
import fs from 'node:fs/promises'
import assert from 'node:assert/strict'
import {execFileSync} from 'node:child_process'
import os from 'node:os'
const base='http://127.0.0.1:8770',out=process.env.BIOREACTOR_DIALOGUE_OUT??'../reports/three_turn_qwen_retest_20261112'
await fs.mkdir(out,{recursive:true})
const questions=JSON.parse(await fs.readFile('../reports/web_only_consultant_20261112/questions.json','utf8'))
const argument=name=>process.argv.find(x=>x.startsWith(name+'='))?.slice(name.length+1)
const resumePath=argument('--resume'),messagePath=argument('--message-file')
const suitePath=argument('--suite-file')
const saved=resumePath?JSON.parse(await fs.readFile(resumePath,'utf8')):null
const startTurn=saved?.turns.length??0
if(saved){assert.equal(startTurn,2);assert.equal(saved.turns[0].job.conversation_id,saved.turns[1].job.conversation_id)}
if(messagePath){assert.ok(saved,'Custom third turn requires a saved dialogue');const bytes=await fs.readFile(messagePath);const text=new TextDecoder('utf-8',{fatal:true}).decode(bytes);assert.ok(Buffer.from(text).equals(bytes));questions[2]=text.trim()}
const strictCooldown=process.argv.includes('--reproducible-cooldown')
function sample(){return JSON.parse(execFileSync('python',['-X','utf8','-c','import json; from evaluations import qwen4b_manual_chat as q; n=q.WindowsLowMemory(); r=q.telemetry.sample(0); issues=q.calibration_issues(r,n.low(),admission=True); n.close(); print(json.dumps({"measurement":r,"issues":issues}))'],{cwd:'..',encoding:'utf8',timeout:20000}))}
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true})
const record={turns:saved?[...saved.turns]:[],errors:[],preflight:[],scope:'Actual browser, actual backend; model status recorded separately',resumed_from:resumePath??null,reused_prior_turns:startTurn,cooling_policy:strictCooldown?'optional_baseline_plus_2_reproducibility':'mandatory_resource_guards_only'}
try{
 const page=await browser.newPage({viewport:{width:1280,height:900}})
 page.on('pageerror',e=>record.errors.push(e.message))
 if(saved){
  const sid=saved.turns[0].job.conversation_id
  const snapshot=await(await page.request.get(base+'/api/dashboard/chat/sessions/'+sid)).json()
  assert.equal(snapshot.turns.length,startTurn,'Unexpected session history: refusing replay')
  assert.equal(snapshot.state_version,startTurn)
  await page.addInitScript(id=>localStorage.setItem('bioreactor_chat_session_v4',id),sid)
 }
 await page.goto(base+'/dashboard/#/chat')
 if(suitePath){
  if(process.argv.includes('--preflight-in-backend')){
   const capability=await(await page.request.get(base+'/api/dashboard/status')).json()
   assert.equal(capability.experimental_chat?.enabled,true,'Guarded backend required')
   assert.equal(capability.experimental_chat?.model,'qwen3:4b-q4_K_M')
   record.admission_location='mandatory existing guarded backend; no duplicate Python sampler'
  }
  const suite=JSON.parse(await fs.readFile(suitePath,'utf8'));record.suite_origin=suite.origin;record.cases=[]
  const sessions=new Map();let stopped=false
  const save=()=>fs.writeFile(out+'/browser.json',JSON.stringify(record,null,2))
  for(const test of suite.cases){
   const entry={id:test.id,criteria:test.criteria,turns:[]};record.cases.push(entry)
   if(test.continue_case){
    const sid=sessions.get(test.continue_case);assert.ok(sid,'Missing source conversation')
    await page.evaluate(id=>localStorage.setItem('bioreactor_chat_session_v4',id),sid);await page.reload()
   }else{await page.getByRole('button',{name:'Новый диалог',exact:true}).click()}
   if(process.argv.includes('--no-llm'))await page.getByLabel('Режим агента').selectOption('no_llm')
   for(const question of test.questions){
    if(!process.argv.includes('--no-llm')&&process.argv.includes('--preflight-in-backend')){
     // Let browser startup allocations settle without launching another sampler.
     // This bounded readiness wait supplements, never replaces, backend admission.
     const deadline=Date.now()+30000;entry.browser_ram_readiness=[]
     let freeRam
     do{
      freeRam=os.freemem()/1048576
      entry.browser_ram_readiness.push({timestamp:new Date().toISOString(),free_ram_mib:Math.round(freeRam*10)/10})
      if(freeRam>=6656)break
      await page.waitForTimeout(1000)
     }while(Date.now()<deadline)
     await save()
     if(freeRam<6656){entry.status='BLOCKED';entry.block_reason='browser_ready_ram_below_6656_after_30s';stopped=true;break}
    }
    if(!process.argv.includes('--no-llm')&&!process.argv.includes('--preflight-in-backend')){
     const pre=sample();entry.preflight=pre;await save()
     if(pre.issues.length){entry.status='BLOCKED';stopped=true;break}
    }
    await page.getByTestId('chat-input').fill(question)
    const accepted=page.waitForResponse(r=>r.request().method()==='POST'&&/\/sessions\/[^/]+\/jobs$/.test(new URL(r.url()).pathname))
    await page.getByTestId('send-chat').click();const job=await(await accepted).json();sessions.set(test.id,job.conversation_id)
    let result;const deadline=Date.now()+140000
    do{result=await(await page.request.get(base+job.result_reference)).json();if(result.terminal)break;await page.waitForTimeout(250)}while(Date.now()<deadline)
    if(!result?.terminal)await page.request.post(base+'/api/dashboard/jobs/'+job.id+'/cancel')
    const turn={question,job,result};entry.turns.push(turn);await save()
    const reply=result?.reply,guard=reply?.technical_metadata?.experimental_qwen4b
    if(result?.status!=='COMPLETED'){
     turn.transport='FAILED';turn.events=await(await page.request.get(base+'/api/dashboard/jobs/'+job.id+'/events')).json();stopped=true;break
    }
    const generated=Boolean(guard?.provider_calls.some(c=>c.model==='qwen3:4b-q4_K_M'&&c.metrics?.some(m=>m.generation_received)))
    if(process.argv.includes('--preflight-in-backend'))assert.equal(guard?.limits?.admission_ram_mib,6656,'Mandatory admission must remain active')
    turn.real_generation=generated;turn.model_answer_accepted=generated&&reply.technical_metadata.final_author?.startsWith('qwen_')
    turn.model_status=turn.model_answer_accepted?'ACCEPTED_PENDING_INDEPENDENT_REVIEW':generated?'REJECTED_OR_FALLBACK':'NO_MODEL_GENERATION'
    const snapshot=await(await page.request.get(base+'/api/dashboard/chat/sessions/'+job.conversation_id)).json()
    turn.history_snapshot=snapshot
    await page.waitForFunction(n=>document.querySelectorAll('[data-testid="chat-result"]').length>=n,snapshot.turns.filter(t=>t.reply).length)
    await page.reload();await page.waitForFunction(n=>document.querySelectorAll('[data-testid="chat-result"]').length>=n,snapshot.turns.filter(t=>t.reply).length)
    turn.reload_restored=true;await page.screenshot({path:out+'/'+test.id+'.png',fullPage:true})
    if(guard?.status==='blocked'||guard?.stop_reason||(generated&&guard?.unload?.status!=='UNLOADED')){stopped=true;break}
    if(guard?.provider_calls.some(c=>/CUDA|runner.*crash|out of memory/i.test(c.error??''))){stopped=true;break}
   }
   await save();console.log(JSON.stringify({case:test.id,status:entry.status??entry.turns.at(-1)?.model_status,turns:entry.turns.length}))
   if(stopped)break
  }
  record.suite_status=stopped?'STOPPED':'COMPLETED_PENDING_CONTENT_REVIEW';await save()
 }else{
 if(process.argv.includes('--no-llm'))await page.getByLabel('Режим агента').selectOption('no_llm')
 for(let i=startTurn;i<questions.length;i++){
  if(!process.argv.includes('--no-llm')){
   const until=Date.now()+60000;let pre
   do{pre=sample();record.preflight.push(pre)
    const baseline=saved?.preflight?.[0]?.measurement.gpu.temperature_c??record.preflight[0].measurement.gpu.temperature_c
    const cooled=!strictCooldown||i===0||pre.measurement.gpu?.temperature_c<=baseline+2
    if(!pre.issues.length&&cooled)break
    if(!strictCooldown||pre.issues.some(x=>x!=='gpu_temperature_limit'))break
    if(Date.now()+10000>=until)break
    await page.waitForTimeout(10000)
   }while(Date.now()<until)
   const baseline=saved?.preflight?.[0]?.measurement.gpu.temperature_c??record.preflight[0].measurement.gpu.temperature_c
   if(pre.issues.length||(strictCooldown&&i>0&&pre.measurement.gpu.temperature_c>baseline+2)){record.blocked_before_turn=i+1;record.interface_status='BLOCKED';break}
  }
  await page.getByTestId('chat-input').fill(questions[i])
  const accepted=page.waitForResponse(r=>r.request().method()==='POST'&&/\/sessions\/[^/]+\/jobs$/.test(new URL(r.url()).pathname))
  await page.getByTestId('send-chat').click();const job=await(await accepted).json()
  let result;const until=Date.now()+140000
  do{result=await(await page.request.get(base+job.result_reference)).json();if(result.terminal)break;await page.waitForTimeout(250)}while(Date.now()<until)
  if(!result?.terminal)await page.request.post(base+'/api/dashboard/jobs/'+job.id+'/cancel')
  record.turns.push({question:questions[i],job,result});await fs.writeFile(out+'/browser.json',JSON.stringify(record,null,2))
  assert.equal(result.status,'COMPLETED');const reply=result.reply
  if(!process.argv.includes('--no-llm')){
   const guard=reply.technical_metadata.experimental_qwen4b
   assert.ok(guard?.provider_calls.some(c=>c.model==='qwen3:4b-q4_K_M'&&c.metrics?.some(m=>m.generation_received)),'Actual Qwen generation required')
   assert.ok(reply.technical_metadata.final_author.startsWith('qwen_'),'No fallback counted as Qwen acceptance')
   assert.equal(guard.unload.status,'UNLOADED')
  }
  assert.equal(reply.memory.facts.quantity.value,78);assert.equal(reply.memory.facts.reactor_total_volume_l.value,200)
  assert.ok(reply.tools.length>0)
  if(i)assert.equal(reply.memory.assumptions.temperature_c.value,25)
  if(i===2){assert.deepEqual(reply.memory.advanced.temperature_comparison_c,[25,35]);assert.ok(reply.answer.includes('Сравнение')||reply.user_facing_answer.sections.some(s=>s.title==='Сравнение температур'))}
  await page.waitForFunction(n=>document.querySelectorAll('[data-testid="chat-result"]').length>=n,i+1)
  await page.reload();await page.waitForFunction(n=>document.querySelectorAll('[data-testid="chat-result"]').length>=n,i+1)
  await page.screenshot({path:out+`/turn_${i+1}.png`,fullPage:true})
  if(reply.technical_metadata.experimental_qwen4b?.stop_reason)break
 }
 if(!record.blocked_before_turn){assert.equal(record.turns.length,3);assert.equal(record.errors.length,0);record.interface_status='PASSED'}
 console.log(JSON.stringify({interface:record.interface_status,models:record.turns.map(t=>t.result.reply.technical_metadata.experimental_qwen4b?.status)}))
 }
}catch(e){record.interface_status='FAILED';record.error=String(e);throw e}
finally{await fs.writeFile(out+'/browser.json',JSON.stringify(record,null,2));await browser.close()}
