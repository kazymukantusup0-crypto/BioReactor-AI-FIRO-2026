import {useEffect,useRef,useState} from 'react'
import {Play,FlaskConical,MessageSquare,ShieldCheck} from 'lucide-react'
import {firoApi,type DemoRun} from '../firoDemo'
import {useQuery} from '../hooks'
import {Badge,Panel,Notice,LoadState,JsonDetails,number} from '../ui'

const KEY='bioreactor-firo-mvp-run'
const provenance:Record<string,string>={CALCULATED:'Рассчитано',MEASURED:'Расчёт по измеренным входам',LITERATURE_ESTIMATE:'Литературная оценка',INSUFFICIENT_EVIDENCE:'Недостаточно научных данных',USER_INPUT:'Демонстрационный ввод',LITERATURE:'Научный источник',UNAVAILABLE:'Не установлено'}
export default function FiroDemoMvp(){
  const catalog=useQuery('firo-mvp',firoApi.scenarios)
  const [run,setRun]=useState<DemoRun|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[model,setModel]=useState(false)
  const active=useRef(''),mounted=useRef(true)
  useEffect(()=>{mounted.current=true;const controller=new AbortController();const id=localStorage.getItem(KEY)
    if(id){active.current=id;firoApi.get(id,controller.signal).then(r=>{if(mounted.current&&active.current===r.id)setRun(r)}).catch(()=>{})}
    return()=>{mounted.current=false;controller.abort()}
  },[])
  useEffect(()=>{
    if(!run||run.explanation.status!=='generating')return
    const controller=new AbortController();let timer:ReturnType<typeof setTimeout>
    const poll=async()=>{try{const next=await firoApi.get(run.id,controller.signal);if(!controller.signal.aborted&&active.current===next.id){setRun(next);if(next.explanation.status==='generating')timer=setTimeout(poll,1000);else setBusy(false)}}catch{if(!controller.signal.aborted)timer=setTimeout(poll,2000)}}
    timer=setTimeout(poll,1000);return()=>{clearTimeout(timer);controller.abort()}
  },[run?.id,run?.explanation.status])
  const explain=async(value:DemoRun)=>{
    setBusy(true);setError('');setRun({...value,explanation:{status:'generating',text:null,message:'Qwen объясняет проверенный результат…'}})
    try{const next=await firoApi.explain(value.id);if(mounted.current&&active.current===next.id)setRun(next)}
    catch(e){if(mounted.current){setError((e as Error).message);try{const next=await firoApi.get(value.id);if(active.current===next.id)setRun(next)}catch{}}}
    finally{if(mounted.current&&active.current===value.id)setBusy(false)}
  }
  const start=async(id:string)=>{setBusy(true);setError('');try{const next=await firoApi.run(id);active.current=next.id;localStorage.setItem(KEY,next.id);if(mounted.current)setRun(next);if(model)await explain(next)}catch(e){if(mounted.current)setError((e as Error).message)}finally{if(mounted.current)setBusy(false)}}
  const cancel=async()=>{if(!run)return;try{const next=await firoApi.cancel(run.id);if(mounted.current&&active.current===next.id)setRun(next)}catch(e){setError((e as Error).message)}}
  return <div className="firo-mvp" data-testid="firo-mvp">
    <LoadState loading={catalog.loading} error={catalog.error} retry={catalog.refresh}/>
    {catalog.data&&!catalog.data.enabled?<Notice>Экспериментальный режим не включён. Запуск: <code>python -X utf8 main.py dashboard --firo-demo --port 8770</code></Notice>:null}
    {catalog.data?.enabled&&<>
      <Panel title="FIRO Demo MVP" subtitle="Три научных сценария. Расчёты и ограничения готовы без языковой модели." action={<Badge tone="amber">Экспериментальный режим</Badge>}>
        <label className="firo-model-toggle"><input type="checkbox" checked={model} disabled={busy} onChange={e=>setModel(e.target.checked)}/> Добавлять пояснение Qwen3 4B после проверки ресурсов</label>
        <div className="firo-scenario-grid">{catalog.data.scenarios.map((s,index)=><article key={s.id} className="firo-scenario"><span className="eyebrow">СЦЕНАРИЙ {String.fromCharCode(65+index)}</span><h3>{s.title.slice(4)}</h3><p>{s.question}</p><ul>{s.inputs.map(input=><li key={input.label}>{input.label}: {number(input.value)} {input.unit}</li>)}</ul><button className="btn btn-primary" disabled={busy} onClick={()=>start(s.id)}><Play size={14}/>Запустить {String.fromCharCode(65+index)}</button></article>)}</div>
      </Panel>
      {error&&<div role="alert"><Notice tone="red">{error}</Notice></div>}
      {run&&<div data-testid="firo-result" aria-live="polite">
        <Panel title={run.title} subtitle={run.input_notice} action={<Badge tone="cyan">{run.verification.label}</Badge>}>
          <h3>Исходные данные</h3><p className="firo-question">{run.question}</p>
          {run.estimate&&<Notice><strong>Режим: {provenance[run.estimate.estimation_mode]??'Не подтверждено'}</strong>. Литературные параметры относятся к опубликованному образцу. Они не являются измерениями вашей партии. Выход за срок показывается отдельно от BMP-ориентира.</Notice>}
          <div className="firo-result-grid"><section><h3><FlaskConical size={17}/>Проверенные результаты Python</h3>{run.results.map(result=><div className="firo-value" key={result.label}><span>{result.label}</span><strong>{result.value===null?'Не установлено':typeof result.value==='number'?number(result.value,6):result.value} {result.unit}</strong><Badge>{provenance[result.provenance]??'Не подтверждено'}</Badge>{result.formula&&<p className="firo-formula">{result.formula}</p>}</div>)}</section>
            <section><h3><ShieldCheck size={17}/>Научный ответ</h3><p className="firo-answer" data-testid="firo-answer">{run.answer}</p></section></div>
          {run.missing.length>0&&<div className="firo-missing"><h3>Каких данных не хватает</h3><ul>{run.missing.map(x=><li key={x}>{x}</li>)}</ul></div>}
          {run.questions.length>0&&<div className="firo-questions"><h3>Уточните для продолжения</h3>{run.questions.map(x=><p key={x}>{x}</p>)}</div>}
          {run.sources.length>0&&<div className="source-links">{run.sources.map(s=><a href={s.url} target="_blank" rel="noreferrer" key={s.url}>{s.title}{s.year?` (${s.year})`:''}</a>)}</div>}
          <JsonDetails value={run.verification} title="Проверка расчёта и научных ограничений"/>
        </Panel>
        <Panel title="Пояснение Qwen3 4B" action={<MessageSquare size={18}/>}>
          <p role="status">{run.explanation.message}</p>
          {run.explanation.text&&<p className="firo-answer" data-testid="firo-model-answer">{run.explanation.text}</p>}
          <div className="firo-actions"><button className="btn btn-secondary" disabled={busy||run.explanation.status==='generating'} onClick={()=>explain(run)}>Получить пояснение Qwen3 4B</button>{run.explanation.status==='generating'&&<button className="btn btn-secondary" onClick={cancel}>Остановить пояснение</button>}</div>
          <small className="muted">Основной ответ выше сохраняется, даже если модель недоступна или её пояснение отклонено.</small>
          <JsonDetails value={{tools:run.tools,explanation:run.explanation}} title="Фактические инструменты и диагностика модели"/>
        </Panel>
      </div>}
    </>}
  </div>
}
