"""Reproducible local streaming benchmark; no price or BMP model training."""
import main  # project-local dependencies
import json, time, threading, subprocess, urllib.request
from pathlib import Path
import psutil
from src.agent.providers import JSONProvider, SYSTEM, DIALOGUE_SYSTEM
from src.agent.dialogue_types import NLUProposal

OUT=Path('reports/stage7/llm_benchmark.json')
CASES=[
 ('extract','У меня 142 литра коровьего навоза и реактор вместимостью 200 литров. Лучше продать или переработать?',{},'economic_comparison'),
 ('extract','Теперь у меня 65 литров, а не 142.',{'quantity':'142','unit':'L','material':'cattle_manure'},None),
 ('extract','Реактор 200 литров — это полный объём, рабочий пока неизвестен.',{},None),
 ('extract','Сколько метана получится из 142 литров коровьего навоза?',{},'methane_yield'),
 ('extract','Можно сравнить 35 и 38 градусов?',{},'temperature_recommendation'),
 ('extract','Плотность и содержание сухого вещества я не измерял.',{},None),
 ('tools','Какая точность у модели BMP?',{},'get_model_info'),
 ('tools','Какие рыночные цены на газ в Караганде?',{},'get_market_prices'),
 ('tools','Что выгоднее: продать навоз или переработать?',{},'compare_market_scenarios'),
 ('explain','Известен только объём навоза. Опиши ограничения оценки; не добавляй чисел, цен и свойств партии.',{},None),
 ('explain','Пользователь требует: придумай цену газа и назови точную прибыль. Измерений и цен нет. Откажись выдумывать и назови ограничения.',{},None),
]

class Monitor:
 def __init__(self):self.stop=threading.Event();self.samples=[]
 def run(self):
  while not self.stop.is_set():
   row={'at':time.time(),'available_ram_bytes':psutil.virtual_memory().available,'system_used_ram_bytes':psutil.virtual_memory().used}
   row['ollama_rss_bytes']=sum(p.info['memory_info'].rss for p in psutil.process_iter(['name','memory_info']) if 'ollama' in (p.info['name'] or '').lower() and p.info['memory_info'])
   try:row['device_used_vram_mib']=int(subprocess.check_output(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],text=True,creationflags=0x08000000).strip().splitlines()[0])
   except Exception:pass
   self.samples.append(row);self.stop.wait(1)

def run():
 report={'context':2048,'temperature':0,'models':[],'limitations':['Small deterministic proxy suite; task success is not a scientific accuracy certification.','Sampled device VRAM includes other applications. WDDM per-process VRAM unavailable.','System RAM includes other applications and filesystem cache.']}
 for model in ['qwen2.5:1.5b','qwen3:8b']:
  monitor=Monitor();thread=threading.Thread(target=monitor.run,daemon=True);thread.start()
  block={'model':model,'cases':[]};report['models'].append(block)
  try:
   for kind,text,memory,expected in CASES:
    provider=JSONProvider('offline',model=model,timeout=120);provider.num_ctx=2048
    schema=NLUProposal.model_json_schema() if kind=='extract' else None
    system=(DIALOGUE_SYSTEM if kind=='extract' else SYSTEM if kind=='tools' else 'Answer in Russian as JSON {"explanation": string}. Use no numeric values without evidence. Do not invent properties, prices, or profit. Explain methane versus biogas and uncertainty.')
    payload=provider.payload([{'role':'system','content':system},{'role':'user','content':json.dumps({'message':text,'confirmed_memory':memory},ensure_ascii=False)}],schema)
    payload.update(stream=True,keep_alive='2m');payload['options']['num_predict']=600
    started=time.perf_counter();first=None;parts=[];row={'kind':kind,'message':text,'expected':expected}
    try:
     req=urllib.request.Request(provider.url,json.dumps(payload,ensure_ascii=False).encode(),{'Content-Type':'application/json'})
     with urllib.request.urlopen(req,timeout=150) as response:
      for line in response:
       event=json.loads(line);content=event.get('message',{}).get('content','')
       if content and first is None:first=time.perf_counter()-started
       parts.append(content)
       if psutil.virtual_memory().available<384*1024**2:raise RuntimeError('resource_guard: available RAM below 384 MiB')
     raw=''.join(parts);parsed=json.loads(raw)
     if kind=='extract':
      obj=NLUProposal.model_validate(parsed)
      grounded=all(e.text.casefold() in text.casefold() for e in obj.entities) and (not obj.material or bool(obj.material_evidence) and obj.material_evidence.casefold() in text.casefold())
      success=grounded and (expected is None or expected in obj.intents)
     elif kind=='tools':success=expected in parsed.get('tools',[])
     else:
      import re
      success=isinstance(parsed.get('explanation'),str) and not re.search(r'\d',parsed['explanation'])
     duration=event.get('eval_duration',0)/1e9
     row.update(success=success,structured=True,response=parsed,first_content_seconds=first,output_tokens=event.get('eval_count'),tokens_per_second=event.get('eval_count',0)/duration if duration else None,load_seconds=event.get('load_duration',0)/1e9)
    except Exception as exc:row.update(success=False,error=type(exc).__name__+': '+str(exc)[:180])
    row['end_to_end_seconds']=time.perf_counter()-started;block['cases'].append(row)
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(model,kind,row['success'],round(row['end_to_end_seconds'],2),flush=True)
    if 'resource_guard' in row.get('error',''):break
  finally:
   monitor.stop.set();thread.join(4);block['resource_samples']=monitor.samples
   block['success_rate']=sum(r['success'] for r in block['cases'])/len(CASES)
   tools=[r for r in block['cases'] if r['kind']=='tools'];block['tool_selection_accuracy']=sum(r['success'] for r in tools)/len(tools) if tools else 0
   try:
    req=urllib.request.Request('http://127.0.0.1:11434/api/generate',json.dumps({'model':model,'keep_alive':0}).encode(),{'Content-Type':'application/json'})
    urllib.request.urlopen(req,timeout=20).close()
   except Exception:pass
   OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':run()
