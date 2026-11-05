import main,json,time
from src.data.prepare import ROOT
from src.agent.conversation import ConversationAgent
from src.agent.providers import HybridLLM
from src.agent.tools import ToolRegistry
from src.market.store import Store
out=ROOT/'reports/stage8_0'
sequences=[['У меня 156 литров навоза с подстилкой и реактор на 200 литров. Рассчитай биогаз, тепло, электричество, затраты и выгоду','Коровий','А если 200 литров?','А если добавить 20 кг соломы?','Какая температура лучше?','А сколько это стоит?'],['У меня 50 кг сухого коровьего навоза','А если он свежий?','Добавь 20 кг пищевых отходов','Переведи всё в литры','Какая температура лучше?','Сколько дней потребуется?','Что выгоднее — продать или переработать?','Объясни простыми словами','Ответь одним предложением','Почему ты использовал такую плотность?']]
rows=[]
for questions in sequences:
 a=ConversationAgent(llm=HybridLLM(providers=[]),registry=ToolRegistry(Store(out/'baseline_dialogue.sqlite3')),research_enabled=True)
 for q in questions:
  r=a.ask(q);print(q,'\n',r['answer'],'\n',r.get('pending_question'),flush=True);rows.append({'question':q,'reply':r})
(out/'smoke.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
