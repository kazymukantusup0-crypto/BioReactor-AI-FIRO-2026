import { chromium } from 'playwright-core'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import path from 'node:path'

const output=path.resolve('../reports/stage8_5')
await fs.mkdir(output,{recursive:true})
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true,args:['--disable-gpu']})
const page=await browser.newPage({viewport:{width:1440,height:1000}})
const errors=[]; const checks=[]
page.on('pageerror',e=>errors.push(e.message))
const check=(name,condition)=>{assert.ok(condition,name);checks.push(name)}
try {
  await page.goto('http://127.0.0.1:8769/dashboard/#/substrates',{waitUntil:'networkidle'})
  await page.getByTestId('material-0').selectOption('food_waste')
  await page.getByTestId('state-0').selectOption('prepared_pulp')
  await page.getByTestId('quantity-0').fill('5')
  await page.getByTestId('reactor-total').fill('90')
  await page.getByTestId('market-region').fill('KZ-Karaganda-oblast')
  const modes=page.locator('.advisor-page .display-mode button')
  check('Simple mode default',await modes.nth(0).getAttribute('aria-pressed')==='true')
  await modes.nth(1).click()
  await page.getByTestId('profile-0').selectOption('baek2020-food-pulp')
  await modes.nth(0).click()
  check('Mode switch preserves quantity',await page.getByTestId('quantity-0').inputValue()==='5')
  await modes.nth(1).click()
  check('Mode switch preserves source profile',await page.getByTestId('profile-0').inputValue()==='baek2020-food-pulp')
  const calculated=page.waitForResponse(r=>r.url().endsWith('/api/advisor/analyze') && r.request().method()==='POST'
    && r.request().postDataJSON().region_confirmed===true)
  await page.getByTestId('region-confirmed').check()
  const response=await calculated
  const payload=response.request().postDataJSON()
  const result=await response.json()
  check('Calculation sends typed state',payload.components[0].quantity===5 && payload.reactor_total_volume_l===90 && payload.region==='KZ-Karaganda-oblast')
  const scenario=result.scenario_results?.[0]??result
  check('Scientific calculation returns methane',scenario.mixture?.additive_methane_reference_m3?.low>0)
  await page.screenshot({path:path.join(output,'calculator.png'),fullPage:true})
  const handoffResponse=page.waitForResponse(r=>r.url().endsWith('/api/advisor/handoff') && r.status()===201)
  await page.getByTestId('send-to-chat').click()
  const handoff=await (await handoffResponse).json()
  await page.getByTestId('open-calculator').waitFor({state:'visible'})
  const memory=await page.evaluate(async id=>(await (await fetch('/api/dashboard/chat/sessions/'+id)).json()).memory,handoff.session_id)
  const c=memory.advanced.inventory[0]
  check('Calculator to chat keeps full component',c.material==='food_waste' && c.quantity===5 && c.unit==='kg' && c.material_state==='prepared_pulp' && c.reference_profile_id==='baek2020-food-pulp')
  check('Calculator to chat keeps region and capacity',memory.facts.market_region.value==='KZ-Karaganda-oblast' && memory.facts.reactor_total_volume_l.value===90)
  await page.screenshot({path:path.join(output,'chat_handoff.png'),fullPage:true})
  await page.getByTestId('open-calculator').click()
  // Hydration occurs before asynchronous catalog options arrive. Check values
  // after the options have loaded, in one DOM snapshot rather than mixed times.
  await page.waitForFunction(()=>document.querySelector('[data-testid="material-0"]')?.value==='food_waste'
    && document.querySelector('[data-testid="state-0"]')?.value==='prepared_pulp'
    && document.querySelector('[data-testid="profile-0"]')?.value==='baek2020-food-pulp')
  const values=await page.evaluate(()=>Object.fromEntries(['material-0','state-0','profile-0','quantity-0','reactor-total','market-region'].map(id=>[id,document.querySelector(`[data-testid="${id}"]`).value])))
  check('Chat to calculator retains material form and profile',values['material-0']==='food_waste' && values['state-0']==='prepared_pulp' && values['profile-0']==='baek2020-food-pulp')
  check('Chat to calculator retains amount capacity region',values['quantity-0']==='5' && values['reactor-total']==='90' && values['market-region']==='KZ-Karaganda-oblast')
  check('Chat import opens scientific mode',await page.locator('.advisor-page .display-mode button').nth(1).getAttribute('aria-pressed')==='true')
  check('No browser JavaScript exceptions',errors.length===0)
  await page.screenshot({path:path.join(output,'chat_to_calculator.png'),fullPage:true})
  if(process.env.STAGE85_LIVE_BROWSER==='1') {
    page.setDefaultTimeout(180000)
    const transferred=page.waitForResponse(r=>r.url().endsWith('/api/advisor/handoff') && r.status()===201)
    await page.getByTestId('send-to-chat').click()
    await transferred
    await page.locator('#chat-input').fill('Сколько метана и полезной энергии в этой партии?')
    const generated=page.waitForResponse(r=>r.url().includes('/api/dashboard/chat/sessions/') && r.url().endsWith('/messages') && r.request().method()==='POST',{timeout:200000})
    await page.locator('.send-button').click()
    const reply=await (await generated).json()
    check('Browser chat uses actual Qwen3 8B',reply.provider_status.some(p=>p.model==='qwen3:8b' && p.actual_generation))
    const science=reply.tools.find(t=>t.tool==='assess_substrate_potential')?.result
    check('Browser chat computes same methane',Math.abs(science.scenarios[0].methane_m3.low-scenario.mixture.additive_methane_reference_m3.low)<1e-10)
    check('Browser chat retains known region',reply.memory.facts.market_region.value==='KZ-Karaganda-oblast')
    await fs.writeFile(path.join(output,'browser_live_reply.json'),JSON.stringify(reply,null,2))
    await page.screenshot({path:path.join(output,'chat_live.png'),fullPage:true})
  }
  await fs.writeFile(path.join(output,'browser_checks.json'),JSON.stringify({passed:true,checks,errors,values,browser:browser.version()},null,2))
  console.log(JSON.stringify({passed:true,checks:checks.length,values},null,2))
} catch(error) {
  await page.screenshot({path:path.join(output,'browser_failure.png'),fullPage:true})
  await fs.writeFile(path.join(output,'browser_failure.json'),JSON.stringify({error:String(error),checks,errors},null,2))
  throw error
} finally {await browser.close()}
