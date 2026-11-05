import main
import tempfile,os,sqlite3,json
from pathlib import Path
from contextlib import closing
from src.agent.conversation import ConversationAgent
from src.agent.providers import HybridLLM
from src.agent.tools import ToolRegistry
from src.market.store import Store
os.environ['BIOREACTOR_RESEARCH_ONLINE']='0'
with tempfile.TemporaryDirectory() as tmp:
    db=Path(tmp)/'qa.sqlite3'
    with closing(sqlite3.connect('reports/stage7_7/baseline.sqlite3')) as source,closing(sqlite3.connect(db)) as target:source.backup(target)
    a=ConversationAgent(llm=HybridLLM(providers=[]),registry=ToolRegistry(Store(db)),research_enabled=True)
    for q in ['У меня 142 литра коровьего навоза. Сколько газа получится?','Какая температура лучше?','Сколько дней потребуется?','Добавь 20 кг пищевых отходов','А теперь сколько газа?','Что выгоднее — продать или переработать?','Объясни подробнее','Ответь одним предложением']:
        r=a.ask(q);print(q,'\n',r['answer'],'\nTOOLS',[(t['tool'],t.get('cache_hit')) for t in r['tools']],r.get('technical_metadata',{}).get('validation_errors'))
