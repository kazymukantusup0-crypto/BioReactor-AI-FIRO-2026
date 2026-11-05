"""Actual CLI compatibility checks against a disposable copy of real saved data."""
import main
import json,os,sqlite3,subprocess,sys,tempfile
from contextlib import closing
from pathlib import Path
from src.data.prepare import ROOT
def run():
    checks=[]
    with tempfile.TemporaryDirectory(prefix='bioreactor-v75-cli-') as tmp:
        db=Path(tmp)/'cli.sqlite3'
        with closing(sqlite3.connect(ROOT/'data/market/market.sqlite3')) as source,closing(sqlite3.connect(db)) as target:source.backup(target)
        env={**os.environ,'PYTHONUTF8':'1','BIOREACTOR_MARKET_DB':str(db),'BIOREACTOR_RESEARCH_ONLINE':'0'}
        def call(args):
            p=subprocess.run([sys.executable,'main.py',*args],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',timeout=120)
            assert p.returncode==0,p.stderr
            return json.loads(p.stdout)
        first=call(['chat','--research','--no-llm','--json','--message','У меня 142 литра коровьего навоза и реактор на 200 литров. Сколько биогаза и что выгоднее?'])
        assert first['analysis_version']=='7.5' and '2.92' in first['answer'];checks.append('Actual v7.5 CLI estimate')
        identifier=first['memory']['conversation_id']
        second=call(['chat','--conversation',identifier,'--no-llm','--json','--message','Навозная жижа'])
        assert second['technical_metadata']['research_result']['result_level']=='LITERATURE_ESTIMATE' and len(second['answer'])<len(first['answer']);checks.append('Persisted compact material clarification')
        third=call(['chat','--conversation',identifier,'--no-llm','--json','--message','Для отопления'])
        assert third['memory']['decision_settings']['gas_use']=='heat' and third['memory']['facts']['reactor_total_volume_l']['value']==200;checks.append('Purpose and 200 L retained')
        old=call(['chat','--no-llm','--json','--message','Какая точность модели BMP?']);assert old['conversation_version']=='5.6';checks.append('Legacy CLI retained')
        for name in ['stage1','stage1_5']:
            assert call(['predict','--model',name,'--input','examples/stage1_5_measured.json'])['bmp']>0;checks.append('Real saved estimator CLI '+name)
        (ROOT/'reports/stage7_5/cli-results.json').write_text(json.dumps({'passed':True,'checks':checks,'reply':third},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':True,'checks':len(checks)}))
if __name__=='__main__':run()
