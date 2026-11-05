"""Repeat only the browser checks after UI changes, preserving the real Ollama results."""
import main
import json,os,subprocess,sys,time,uuid
from verify_stage7_6 import http,BASE,OUT,ROOT
def run():
    report=json.loads((OUT/'http_results.json').read_text(encoding='utf-8'));db=report['database']
    assert str(ROOT/'data/runtime') in db and 'stage7_6_validation' in db
    env={**os.environ,'PYTHONUTF8':'1','BIOREACTOR_MARKET_DB':db,'BIOREACTOR_RESEARCH_ONLINE':'0','BIOREACTOR_MARKET_SCHEDULER':'0'}
    server=subprocess.Popen([sys.executable,'main.py','dashboard','--port','8776','--no-browser','--no-scheduler'],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=0x08000000 if os.name=='nt' else 0)
    try:
        for _ in range(60):
            try:assert http('/health')['database']==db;break
            except OSError:time.sleep(.2)
        else:raise RuntimeError('QA server did not start')
        s=http('/api/dashboard/chat/sessions',{'mode':'no_llm','conversation_version':'7'})['id']
        for q in ['У меня 50 кг коровьего навоза, 20 кг пищевых отходов и 10 кг травы. Что получится, если смешать?','Добавь ещё 5 кг пищевых отходов','Убери траву. Какая температура лучше?','Какая смесь выгоднее?','У меня только 200-литровый реактор. Можно загрузить всё сразу?','Что изменится, если увеличить навоз вдвое?']:
            r=http(f'/api/dashboard/chat/sessions/{s}/messages',{'message':q,'request_id':uuid.uuid4().hex});assert r.get('analysis_version')=='7.6'
        p=subprocess.run(['node','tests/advisor-browser.mjs'],cwd=ROOT/'frontend',env={**env,'BIOREACTOR_QA_ISOLATED':'1','BIOREACTOR_QA_URL':BASE,'BIOREACTOR_QA_SESSION':s},capture_output=True,text=True,encoding='utf-8',timeout=240)
        (OUT/'browser.log').write_text(p.stdout+'\n'+p.stderr,encoding='utf-8');print(p.stdout);print(p.stderr);assert p.returncode==0
        previous=report.pop('error',None)
        if previous:report.setdefault('resolved_verification_errors',[]).append(previous)
        report['checks']=[c for c in report['checks'] if c['name']!='Real Chrome browser workflow']+[{'name':'Real Chrome browser workflow','passed':True}]
        report['browser_session']=s;report['browser_recheck']='Fresh no-LLM browser session; original real Ollama A–F dialogues retained'
        (OUT/'http_results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'passed':True,'checks':len(report['checks'])}))
    finally:server.terminate();server.wait(timeout=15)
if __name__=='__main__':run()
