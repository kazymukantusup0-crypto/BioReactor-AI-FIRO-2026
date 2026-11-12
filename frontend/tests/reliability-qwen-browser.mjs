// P1 real Qwen3 8B, Chrome, production handlers; no intercepted routes/fake provider.
import { chromium } from 'playwright-core'
import fs from 'node:fs/promises'
import path from 'node:path'
const base=process.env.BIOREACTOR_QA_URL||'http://127.0.0.1:8773';const out=path.resolve('../reports/reliability')
const label='p1_qwen_browser_'+new Date().toISOString().replace(/[:.]/g,'-')
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true,args:['--disable-gpu']})
const context=await browser.newContext({viewport:{width:1440,height:1000}})
const page=await context.newPage();const checks=[];const errors=[];let session;let job;let snapshot
page.on('pageerror',e=>errors.push(String(e)))
const check=(name,value)=>checks.push({name,passed:Boolean(value)})
try {
  session=await(await context.request.post(base+'/api/dashboard/chat/sessions',{data:{mode:'offline',context:{},conversation_version:'7'}})).json()
  await context.addInitScript(id=>localStorage.setItem('bioreactor_chat_session_v4',id),session.id)
  await page.goto(base+'/dashboard/#/chat')
  await page.waitForFunction(()=>document.querySelector('.chat-header select')&&!document.querySelector('.chat-header select').disabled)
  await page.getByTestId('chat-input').fill('У меня 5 кг пищевых отходов и реактор 90 литров. Сколько метана можно получить и выгодно ли его производить?')
  const response=page.waitForResponse(r=>r.url().endsWith('/jobs')&&r.request().method()==='POST')
  await page.getByTestId('send-chat').click();job=await(await response).json()
  await page.getByTestId('job-progress').waitFor();await page.reload()
  await page.getByTestId('chat-result').waitFor({timeout:240000})
  snapshot=await(await context.request.get(base+'/api/dashboard/chat/sessions/'+session.id)).json()
  const done=snapshot.jobs.find(j=>j.id===job.id);const reply=snapshot.turns.find(t=>t.request_id===job.request_id).reply
  const meta=reply.technical_metadata;const scientific=meta.scientific_details??{}
  check('Exact real Qwen3 8B generated',reply.provider_status.some(p=>p.model==='qwen3:8b'&&p.actual_generation))
  check('Actual runtime9 selected tools',Array.isArray(meta.research_actions)&&meta.research_actions.length>0)
  check('Scientific tool called',reply.tools.some(t=>t.tool==='assess_substrate_potential'))
  check('Economic tool called',reply.tools.some(t=>t.tool==='evaluate_partial_economics'))
  check('Applicable calculations independently checked',meta.verification?.outcome==='passed'&&meta.verification?.checked)
  check('Final answer is a verified Qwen synthesis or a checked engine fallback',meta.final_author==='qwen_verified'||meta.final_author==='verified_engine_partial')
  check('Rejected synthesis is diagnosable when engine fallback is used',meta.final_author!=='verified_engine_partial'||(meta.diagnostics.some(d=>d.stage==='synthesis_validation')&&meta.synthesis_rejections.length>0))
  check('Engine fallback starts with its verified partial result',meta.final_author!=='verified_engine_partial'||reply.answer.startsWith('Предварительная оценка по доступным и проверенным данным:'))
  const displayed=meta.verified_display_references??[]
  check('Computed methane reaches answer',displayed.some(r=>r.id.endsWith('.methane'))&&(await page.getByTestId('chat-result').innerText()).includes('м³'))
  check('Available economics displayed',displayed.some(r=>r.id.endsWith('.gross')||r.id.endsWith('_kwh'))||/\bKZT\b|кВт·ч/.test(reply.answer))
  check('Profit remains unestablished',scientific.evaluate_partial_economics?.profit_established===false)
  check('Unknown costs do not become a negative verdict',!/не\s*выгодно|убыточн/i.test(reply.answer))
  check('At most one clarification',reply.answer.split('?').length-1<=1)
  check('No actuation',reply.actuator_access===false)
  check('Reload gives one turn',await page.getByTestId('chat-turn').count()===1)
  check('No double scientific commit',snapshot.state_version===1&&done.attempt_count===1)
  await page.waitForFunction(()=>!document.querySelector('[data-testid="open-calculator"]').disabled)
  // The calculator consumes/removes its transfer key on mount; capture the real write.
  await page.evaluate(()=>{const original=Storage.prototype.setItem;Storage.prototype.setItem=function(key,value){if(key==='bioreactor-chat-to-advisor-v1')window.__qaTransfer=JSON.parse(value);return original.call(this,key,value)}})
  await page.getByTestId('open-calculator').click();await page.getByTestId('quantity-0').waitFor()
  const transfer=await page.evaluate(()=>window.__qaTransfer)
  check('Chat and calculator task_id match backend',transfer.task_id===snapshot.memory.task_id)
  check('Chat and calculator state_version match backend',transfer.state_version===snapshot.state_version)
  check('Calculator retains mass and vessel',await page.getByTestId('quantity-0').inputValue()==='5'&&await page.getByTestId('reactor-total').inputValue()==='90')
  check('No browser exceptions',errors.length===0)
  await page.screenshot({path:path.join(out,label+'.png'),fullPage:true})
  await fs.writeFile(path.join(out,label+'.json'),JSON.stringify({checks,errors,snapshot,browser:browser.version(),configuration:{model:'qwen3:8b',num_gpu:16,num_ctx:8192,num_thread:6,num_batch:64,temperature:0,think:false,agent_timeout:150,job_timeout:180,online_research:false}},null,2))
  console.log(JSON.stringify({artifact:path.join(out,label+'.json'),checks,errors}))
  if(checks.some(c=>!c.passed))process.exitCode=1
}catch(error){await fs.writeFile(path.join(out,label+'_failure.json'),JSON.stringify({checks,errors,session,job,snapshot,error:String(error)},null,2));throw error}
finally{await browser.close()}
