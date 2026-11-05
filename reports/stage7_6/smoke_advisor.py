import main
import os,tempfile,json,traceback
from pathlib import Path
from src.agent.conversation import ConversationAgent
from src.agent.providers import HybridLLM
from src.agent.tools import ToolRegistry
from src.market.store import Store
os.environ['BIOREACTOR_RESEARCH_ONLINE']='0'
with tempfile.TemporaryDirectory() as tmp:
    agent=ConversationAgent(llm=HybridLLM('auto',providers=[]),registry=ToolRegistry(Store(Path(tmp)/'qa.sqlite3')),research_enabled=True)
    for question in ['У меня 50 кг коровьего навоза, 20 кг пищевых отходов и 10 кг травы. Что получится, если всё смешать?', 'Добавь ещё 5 кг пищевых отходов', 'Убери траву. Какая температура лучше?', 'Замени 25 кг пищевых отходов на 15 кг', 'Что изменится, если увеличить навоз вдвое?', 'Какая смесь выгоднее?', 'У меня только 200-литровый реактор. Можно загрузить всё сразу?']:
        try:
            r=agent.ask(question)
            print(question,r.get('mode'),r.get('technical_metadata',{}).get('validation_errors'),[(x['material'],x['quantity'],x['unit']) for x in agent.state.mixture_components]);print(r['answer'])
        except Exception:traceback.print_exc();break
    agent=ConversationAgent(llm=HybridLLM('auto',providers=[]),registry=agent.registry,research_enabled=True)
    r=agent.ask('У меня 142 литра навозной жижи и реактор на 200 литров. Сколько получится газа, какая температура лучше и сколько времени потребуется?')
    print('A',r['answer'],r.get('technical_metadata',{}).get('validation_errors'));print(agent.state.brief())
