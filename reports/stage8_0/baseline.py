import main
import hashlib,json,os,sqlite3,time,shutil
from pathlib import Path
from contextlib import closing
from src.data.prepare import ROOT
from src.market.store import Store
from src.agent.conversation import ConversationAgent
from src.agent.tools import ToolRegistry
from src.agent.providers import HybridLLM
OUT=ROOT/'reports/stage8_0';OUT.mkdir(exist_ok=True)
db=OUT/'baseline.sqlite3'
assert not db.exists(),'Baseline is immutable'
with closing(sqlite3.connect(ROOT/'data/market/market.sqlite3')) as source,closing(sqlite3.connect(db)) as target:source.backup(target)
hashes={}
for folder in ['models','data/raw','data/processed','data/knowledge','data/research','reports']:
    for p in (ROOT/folder).rglob('*'):
        if p.is_file() and OUT not in p.parents:hashes[p.relative_to(ROOT).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
(OUT/'preserved_hashes.json').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
with closing(sqlite3.connect(db)) as con:
    con.row_factory=sqlite3.Row
    old={table:[dict(r) for r in con.execute('SELECT * FROM '+table)] for table in ['observations','dashboard_sessions','dashboard_turns','scenarios','research_records','experiment_records','process_optimizer_runs']}
(OUT/'legacy_sqlite.json').write_text(json.dumps(old,ensure_ascii=False,indent=2),encoding='utf-8')
qa=OUT/'baseline_dialogue.sqlite3'
with closing(sqlite3.connect(db)) as source,closing(sqlite3.connect(qa)) as target:source.backup(target)
os.environ['BIOREACTOR_RESEARCH_ONLINE']='0'
agent=ConversationAgent(llm=HybridLLM('offline'),registry=ToolRegistry(Store(qa)),research_enabled=True)
questions=['У меня 156 литров навоза с подстилкой и реактор на 200 литров. Рассчитай биогаз, тепло, электричество, затраты и выгоду','Коровий','У меня 142 литра коровьего навоза. Сколько газа получится?','Какая температура лучше?','Сколько дней потребуется?','Добавь 20 кг пищевых отходов','А теперь сколько газа?','Что выгоднее — продать или переработать?','Объясни подробнее','Ответь одним предложением']
rows=[]
for q in questions:
    start=time.perf_counter();r=agent.ask(q);rows.append({'question':q,'reply':r,'seconds':time.perf_counter()-start});print(q,round(rows[-1]['seconds'],3),flush=True)
(OUT/'before_dialogue.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')

