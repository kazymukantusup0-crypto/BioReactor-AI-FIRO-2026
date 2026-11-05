import main,hashlib,json,sqlite3,os
from contextlib import closing
from src.data.prepare import ROOT
from src.agent.conversation import ConversationAgent
from src.agent.providers import HybridLLM
from src.agent.tools import ToolRegistry
from src.market.store import Store
from src.advisor import catalog
from src.advisor.service import analyze
out=ROOT/'reports/stage8_1';out.mkdir(exist_ok=True)
assert not (out/'baseline.sqlite3').exists(),'Snapshot is immutable'
with closing(sqlite3.connect(ROOT/'data/market/market.sqlite3')) as source,closing(sqlite3.connect(out/'baseline.sqlite3')) as target:source.backup(target)
hashes={}
for folder in ['models','data/raw','data/processed','data/knowledge','data/research','reports']:
 for p in (ROOT/folder).rglob('*'):
  if p.is_file() and out not in p.parents:hashes[p.relative_to(ROOT).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
(out/'preserved_hashes.json').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
with closing(sqlite3.connect(out/'baseline.sqlite3')) as con:
 con.row_factory=sqlite3.Row
 old={table:[dict(r) for r in con.execute('SELECT * FROM '+table)] for table in ['observations','dashboard_sessions','dashboard_turns','scenarios','research_records','experiment_records','process_optimizer_runs']}
(out/'legacy_sqlite.json').write_text(json.dumps(old,ensure_ascii=False,indent=2),encoding='utf-8')
qa=Store(out/'baseline_qa.sqlite3');os.environ['BIOREACTOR_RESEARCH_ONLINE']='0';rows=[]
for q in ['У меня 100 литров жидкого свиного навоза. Сколько получится газа?','У меня 50 кг сухого куриного помёта. Рассчитай газ, тепло и электричество','Смешай 40 кг коровьего навоза и 20 кг птичьего помёта']:
 a=ConversationAgent(research_enabled=True,llm=HybridLLM(providers=[]),registry=ToolRegistry(qa));reply=a.ask(q);rows.append({'question':q,'reply':reply});print(q,reply['answer'],flush=True)
(out/'before_dialogue.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
audit=[]
for m in catalog.get_catalog()['materials']:
 for state in ['unknown',*m['physical_states']]:
  try:
   r=analyze(qa,{'components':[{'id':'c1','material':m['id'],'material_state':state,'quantity':50,'unit':'kg'}]},persist=False)
   audit.append({'material':m['id'],'state':state,'status':r['status'],'methane':r['mixture']['additive_methane_reference_m3'],'missing':r['mixture']['components'][0]['missing']})
  except Exception as exc:audit.append({'material':m['id'],'state':state,'error':type(exc).__name__+': '+str(exc)})
(out/'before_matrix.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
print('Protected',len(hashes),'files; audited',len(audit),'material/state combinations')
