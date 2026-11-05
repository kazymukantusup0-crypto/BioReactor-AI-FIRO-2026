// Actual Chrome + HTTP backend, exclusively on verify_stage6's isolated SQLite backup.
import { chromium } from 'playwright-core'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import path from 'node:path'
assert.equal(process.env.BIOREACTOR_QA_ISOLATED, '1', 'Refuse to insert TEST records without isolated verification environment')
const base = process.env.BIOREACTOR_QA_URL
assert.ok(base && /^http:\/\/127\.0\.0\.1:\d+$/.test(base))
const out = path.resolve('../reports/stage6')
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true, args: ['--no-first-run', '--disable-background-networking'] })
const context = await browser.newContext({ viewport: { width: 1366, height: 768 }, reducedMotion: 'reduce', locale: 'ru-RU' })
const page = await context.newPage(), checks = [], errors = [], screenshots = [], failedRequests = [], replies = []
page.on('pageerror', error => errors.push(error.message))
page.on('console', message => { if (message.type() === 'error') errors.push(message.text()) })
page.on('requestfailed', request => { if (request.failure()?.errorText !== 'net::ERR_ABORTED') failedRequests.push({url:request.url(),error:request.failure()?.errorText}) })
await context.route('**/*', route => ['127.0.0.1','localhost'].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort())
const check = (label,value=true) => { assert.ok(value,label);checks.push(label) }
const shot = async name => { await page.screenshot({path:path.join(out,name),fullPage:false,animations:'disabled'});screenshots.push(name) }
const response = (method, endpoint) => page.waitForResponse(r => r.url().endsWith(endpoint) && r.request().method()===method,{timeout:120000})
async function field(label,value) {
  const locator=page.getByLabel(label,{exact:true})
  await locator.evaluate(el=>{ for(let parent=el.parentElement;parent;parent=parent.parentElement)if(parent.tagName==='DETAILS')parent.open=true })
  if(await locator.evaluate(el=>el.tagName)==='SELECT')await locator.selectOption(value)
  else await locator.fill(value)
}
async function optimize() {
  const pending=response('POST','/api/process/optimize')
  await page.getByRole('button',{name:'Сравнить и сохранить',exact:true}).click()
  const result=await pending;assert.equal(result.status(),201)
  const data=await result.json();await page.getByTestId('process-results').waitFor();return data
}
try {
  await page.goto(base+'/dashboard/#/optimizer');await page.getByRole('heading',{name:'Process Optimizer',exact:true}).waitFor()
  check('New optimizer navigation resolves')
  check('Unknown input mass stays blank', await page.getByLabel('Масса всей партии',{exact:true}).inputValue()==='')
  check('No default density', await page.getByLabel('Измеренная плотность',{exact:true}).inputValue()==='')
  await shot('optimizer_empty_1366.png')
  await field('Вид сырья','cattle_manure');await field('Объём всей партии','800');await field('Полный объём реактора','90')
  await field('Температура сценария 1','35');await field('Температура сценария 2','38')
  const incomplete=await optimize()
  check('Two user temperature alternatives saved',incomplete.scenarios.length===2)
  check('Unknown working volume is not assigned',incomplete.scenarios.every(s=>s.input_parameters.reactor_working_volume_l===null))
  check('Incomplete scenario has no invented methane',incomplete.scenarios.every(s=>s.predicted_outputs.methane.potential_methane_m3===null))
  check('Incomplete comparison refuses ranking',incomplete.comparison.method==='tradeoff_table')
  check('No fake energy chart',await page.getByTestId('process-energy-chart').count()===0)
  check('Scenario assumptions are visibly disclosed',await page.locator('.process-assumptions').count()===2)
  await page.getByTestId('process-results').evaluate(el=>window.scrollTo({top:window.scrollY+el.getBoundingClientRect().top-90}));await shot('optimizer_incomplete_1366.png')
  for(const [label,value] of Object.entries({'Объём всей партии':'10','Масса всей партии':'10','Подтверждённый рабочий объём':'65',
      'Тип реактора':'TEST explicit vessel','Происхождение и характеристики инокулята':'TEST hypothetical zero-added inoculum scenario',
      'Режим загрузки':'batch','Инокулят в одной загрузке':'0','Вода в одной загрузке':'0','Остаточная жидкость':'0',
      'Длительность цикла':'1','Между партиями':'0','Условия хранения газа':'TEST engineering review not provided',
      'Начальная температура':'20','Температура окружающей среды':'20','Полная нагреваемая масса':'10','Удельная теплоёмкость':'4',
      'КПД нагревателя':'0.8','Коэффициент теплопотерь UA':'2','Период энергобаланса':'1','Насосы и мешалка':'0.1',
      'К чему относится энергобаланс':'entire_feedstock','Масса VS всей партии':'1','BMP из измерения / сценария':'300',
      'Происхождение BMP':'scenario_assumption','Метод/источник BMP или объяснение допущения':'TEST arithmetic illustration, not measured BMP',
      'Условия приведения газа':'TEST dry gas reference'}))await field(label,value)
  await page.getByLabel('Меньше энергозатрат',{exact:true}).check();await page.getByLabel('Больше потенциального CH₄',{exact:true}).check()
  await page.getByText('Диапазоны чувствительности',{exact:true}).click();await page.getByRole('button',{name:'Задать диапазон',exact:true}).click()
  await field('Нижняя граница 1','35');await field('Верхняя граница 1','38');await field('Основание диапазона 1','TEST chosen sensitivity endpoints')
  const physical=await optimize()
  check('SI energy agrees with analytical value',Math.abs(physical.scenarios[0].predicted_outputs.energy.total_energy_kwh-(600/3600/.8+.9+.1))<1e-10)
  check('Temperature alone does not multiply BMP',physical.scenarios.every(s=>s.predicted_outputs.methane.potential_methane_m3===.3))
  check('Explicit complete energy objectives receive conditional Pareto fronts',physical.comparison.method==='pareto_non_dominated_sort')
  await page.getByTestId('process-energy-chart').waitFor();await page.getByTestId('process-methane-chart').waitFor()
  check('Actual computed charts rendered')
  check('Sensitivity uses only supplied range',physical.sensitivity.rows.length===2)
  await page.getByTestId('process-results').evaluate(el=>window.scrollTo({top:window.scrollY+el.getBoundingClientRect().top-90}));await shot('optimizer_results_1366.png')
  await page.setViewportSize({width:1920,height:1080});await shot('optimizer_results_1920.png')
  check('1920 has no document overflow',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1))
  for(const id of [incomplete.id,physical.id])await page.getByLabel(`Выбрать исследование ${id}`,{exact:true}).check()
  const comparisonPending=response('POST','/api/process/compare')
  await page.getByRole('button',{name:'Сравнить выбранные снимки',exact:true}).click()
  const compared=await(await comparisonPending).json();check('History comparison retains all four candidate rows',compared.scenarios.length===4)
  await page.getByRole('heading',{name:'Сравнение технологических сценариев',exact:true}).waitFor()
  check('Historical comparison does not claim optimum with incomplete alternative',compared.comparison.method==='tradeoff_table')
  await page.setViewportSize({width:390,height:844});await page.getByTestId('process-results').evaluate(el=>window.scrollTo({top:window.scrollY+el.getBoundingClientRect().top-90}));await shot('optimizer_mobile.png')
  check('390 has no document overflow',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1))
  await page.setViewportSize({width:1366,height:768});await page.goto(base+'/dashboard/#/experiments')
  await page.getByRole('heading',{name:'Experiment Lab',exact:true}).waitFor();check('Lab navigation resolves')
  await field('Название эксперимента','TEST browser measurement, isolated DB only');await field('Происхождение измерений','user')
  await field('Сырьё','cattle_manure');await field('Измеренный объём биогаза','0.002')
  const createPending=response('POST','/api/experiments');await page.getByRole('button',{name:'Сохранить эксперимент',exact:true}).click()
  const createdResponse=await createPending;assert.equal(createdResponse.status(),201)
  const experiment=await createdResponse.json()
  check('Lab leaves CH4 and VS unknown',experiment.methane_fraction===null && experiment.vs_mass_kg===null)
  await page.getByRole('heading',{name:'Сравнение с прогнозом',exact:true}).waitFor()
  await page.locator('.process-result-message').filter({hasText:'Biogas volume is not methane volume; a measured CH4 fraction is missing'}).waitFor()
  check('Biogas is not presented as measured methane')
  await shot('experiment_lab_1366.png')
  await field('Измеренная температура','35');await field('Измеренный pH','7')
  const measurementPending=response('POST',`/api/experiments/${experiment.id}/measurements`)
  await page.getByRole('button',{name:'Добавить измерение',exact:true}).click()
  assert.equal((await measurementPending).status(),201)
  await page.getByTestId('experiment-chart').waitFor();check('Entered measurements produce actual chart')
  const downloadPending=page.waitForEvent('download');await page.getByRole('link',{name:'Экспорт CSV',exact:true}).click()
  const download=await downloadPending;await download.saveAs(path.join(out,'TEST_lab_export.csv'))
  check('CSV export contains actual TEST record',(await fs.readFile(path.join(out,'TEST_lab_export.csv'),'utf8')).includes('TEST browser measurement'))
  await page.getByRole('button',{name:'Уточнить запись',exact:true}).click()
  check('Origin is immutable in edit form',await page.getByLabel('Происхождение измерений',{exact:true}).count()===0)
  await field('Название эксперимента','TEST revised browser record')
  const updatePending=response('PATCH',`/api/experiments/${experiment.id}`);await page.getByRole('button',{name:'Сохранить эксперимент',exact:true}).click()
  assert.equal((await updatePending).status(),200);check('Experiment edits save successfully')
  await page.reload();await page.getByRole('button',{name:/TEST revised browser record/}).waitFor();check('Experiment persists after reload')
  await page.getByRole('button',{name:/TEST revised browser record/}).click()
  await page.getByTestId('experiment-chart').waitFor();await shot('experiment_measurements_1366.png')
  await page.goto(base+'/dashboard/#/chat');await page.locator('#chat-input').waitFor()
  for(const message of ['У меня 800 литров коровьего навоза и реактор 90 литров. Как лучше его переработать?','Рабочий объём 65 литров','Сравни 35 и 38 градусов','А что выгоднее — продать или переработать?']){
    await page.locator('#chat-input').fill(message)
    const pending=page.waitForResponse(r=>/\/chat\/sessions\/[^/]+\/messages$/.test(r.url()) && r.request().method()==='POST',{timeout:120000})
    await page.getByRole('button',{name:'Отправить сообщение',exact:true}).click()
    const reply=await(await pending).json();replies.push({message,reply})
    await page.waitForFunction(()=>!document.querySelector('#chat-input')?.disabled)
  }
  check('Dashboard chat integrates optimizer',replies[0].reply.policy_tool_plan.includes('optimize_process'))
  check('Dashboard chat retains working volume',replies[3].reply.memory.facts.reactor_working_volume_l.value===65)
  check('Dashboard chat uses real local Ollama',replies.every(r=>r.reply.mode==='llm_tools'))
  await shot('optimizer_chat_1366.png')
  await page.goto(base+'/dashboard/#/reactor');await page.getByRole('heading',{name:'От измерения к наблюдению',exact:true}).waitFor()
  check('Previous reactor page remains available')
  check('No browser errors',errors.length===0);check('No failed requests',failedRequests.length===0)
  await fs.writeFile(path.join(out,'browser.json'),JSON.stringify({passed:true,checks,screenshots,errors,failedRequests,replies,external_requests_blocked:true},null,2))
  console.log(JSON.stringify({passed:true,checks:checks.length,screenshots,actual_ollama_generations:replies.length},null,2))
} catch(error) {
  await fs.writeFile(path.join(out,'browser_failure.json'),JSON.stringify({error:String(error),checks,errors,failedRequests,replies},null,2))
  await page.screenshot({path:path.join(out,'browser_failure.png'),fullPage:true}).catch(()=>{})
  throw error
} finally {await browser.close()}
