"""Actual CLI subprocesses, exclusively against an isolated SQLite backup."""
import main
import json,os,sqlite3,subprocess,sys,tempfile
from contextlib import closing
from pathlib import Path
from src.data.prepare import ROOT
def run():
    checks=[]
    with tempfile.TemporaryDirectory(prefix='bioreactor-v7-cli-') as tmp:
        db=Path(tmp)/'cli.sqlite3'
        with closing(sqlite3.connect(ROOT/'data/runtime/stage7_validation.sqlite3')) as source,closing(sqlite3.connect(db)) as target:source.backup(target)
        env={**os.environ,'PYTHONUTF8':'1','BIOREACTOR_MARKET_DB':str(db),'BIOREACTOR_RESEARCH_ONLINE':'0'}
        def command(args):
            proc=subprocess.run([sys.executable,'main.py',*args],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',timeout=120)
            if proc.returncode:raise RuntimeError(proc.stderr)
            return json.loads(proc.stdout)
        first=command(['chat','--research','--no-llm','--json','--message','У меня 142 литра коровьего навоза и реактор вместимостью 200 литров. Лучше продать или переработать?'])
        assert first['conversation_version']=='7' and '2.92' in first['answer'];checks.append('Actual v7 CLI returns sourced deterministic estimate')
        identifier=first['memory']['conversation_id']
        second=command(['chat','--conversation',identifier,'--no-llm','--json','--message','Навозная жижа'])
        assert second['technical_metadata']['research_result']['result_level']=='LITERATURE_ESTIMATE';checks.append('CLI restores v7 without repeating research flag')
        assert second['memory']['facts']['reactor_total_volume_l']['value']==200;checks.append('CLI retains full vessel capacity')
        old=command(['chat','--no-llm','--json','--message','Какая точность модели BMP?'])
        assert old['conversation_version']=='5.6';checks.append('Legacy CLI contract retained')
        for name in ['stage1','stage1_5']:
            r=command(['predict','--model',name,'--input','examples/stage1_5_measured.json'])
            assert r['bmp']>0;checks.append('Saved estimator CLI '+name)
        output={'passed':True,'checks':checks,'research_reply':second}
        (ROOT/'reports/stage7/cli-results.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'passed':True,'checks':len(checks)}))
if __name__=='__main__':run()
