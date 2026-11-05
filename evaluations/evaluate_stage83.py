"""Real local HTTP/Qwen regression evidence. No mock prices or LLM responses."""
import json,os,time,uuid,urllib.request
from pathlib import Path
BASE=os.getenv('STAGE83_URL','http://127.0.0.1:8767')
OUT=Path(os.getenv('STAGE83_OUTPUT','reports/stage8_3/qwen_http.json'))
CASES=[
 ('cattle48',['У меня 48 литров коровьего навоза и реактор 100 литров. Сколько метана и выгодно ли?']),
 ('grass58',['У меня 58 кг травы и реактор 100 литров. Сколько метана можно получить?']),
 ('poultry50',['У меня 50 кг куриного помёта и реактор 100 литров. Сколько метана и поместится ли загрузка?']),
 ('food5',['У меня 5 кг пищевых отходов и реактор 90 литров. Сколько метана и выгодно ли?']),
 ('mixture',['Смешай 4 кг коровьего навоза, 2 кг травы и 1 кг пищевых отходов. Рассчитай метан и энергию.']),
 ('overfill',['У меня 80 литров навозной жижи КРС, реактор 50 литров. Сколько метана и можно ли загрузить всё сразу?']),
 ('water',['У меня 5 кг пищевых отходов и реактор 90 литров. Сколько метана?', 'Если я добавлю 10 литров воды, метана станет больше?']),
 ('compare',['Что выгоднее: 10 кг коровьего навоза или 10 кг пищевых отходов?']),
 ('temperature',['В реакторе 30 градусов. Стоит ли повышать температуру?']),
 ('costs',['У меня 5 кг пищевых отходов. Сколько денег я заработаю?','Подготовка 100 тенге, транспорт 50 тенге, обслуживание 20 тенге. Пересчитай экономику.']),
 ('pig8',['У меня 8 кг свиного навоза. Сколько биогаза?']),
 ('horse',['Сколько метана из 7 кг конского навоза?']),
 ('goat',['Сколько метана из 3 кг козьего навоза?']),
 ('straw',['Оцени метан из 2 кг пшеничной соломы.']),
 ('silage',['Сколько метана из 12 кг силоса?']),
 ('vegetables',['Сколько метана из 6 кг овощных отходов?']),
 ('fruit',['Сколько метана из 3 кг фруктовых отходов?']),
 ('whey',['Сколько биогаза из 15 литров сыворотки?']),
 ('plant',['Сколько метана из 4 кг растительных остатков?']),
 ('unknown',['Сколько метана из 9 кг другого органического сырья?']),
 ('grass_litres',['Сколько метана из 20 литров травы?']),
 ('poultry_litres',['Сколько метана из 20 литров куриного помёта?']),
 ('food_grams',['Сколько метана из 500 граммов пищевых отходов?']),
 ('pig_tonnes',['Сколько метана из 0,1 тонны свиного навоза?']),
 ('addition',['У меня 5 кг пищевых отходов. Сколько метана?','Добавь 2 кг куриного помёта и пересчитай.']),
 ('correction',['У меня 5 кг пищевых отходов. Сколько метана?','Нет, пищевых отходов 3 кг, пересчитай.']),
 ('temperature_context',['У меня 8 кг свиного навоза и реактор 100 литров. Сколько метана?','Температура 25 градусов. Стоит ли повышать до 35?']),
 ('dry_grass',['Сколько метана из 2 кг сухой травы?']),
 ('compost',['Сколько метана из 5 кг компоста коровьего навоза?']),
 ('mixture_unknown',['Смешай 2 кг пищевых отходов и 1 кг фруктовых отходов. Сколько метана?']),
]

def request(path,data=None):
    req=urllib.request.Request(BASE+path,json.dumps(data,ensure_ascii=False).encode() if data is not None else None,{'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=600) as r:return json.load(r)

def main():
    selected=os.getenv('STAGE83_CASES','').split(',')
    results={'model':'qwen3:8b','http':BASE,'cases':[],'status':'running'}
    for name,messages in CASES:
        if selected!=[''] and name not in selected:continue
        session=request('/api/dashboard/chat/sessions',{'mode':'offline','context':{},'conversation_version':'7'})
        row={'id':name,'session_id':session['id'],'turns':[]};results['cases'].append(row)
        for message in messages:
            start=time.perf_counter()
            try:response=request('/api/dashboard/chat/sessions/'+session['id']+'/messages',{'message':message,'request_id':uuid.uuid4().hex})
            except Exception as exc:response={'error':str(exc)}
            row['turns'].append({'prompt':message,'latency_seconds':time.perf_counter()-start,'response':response})
            OUT.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
            print(name,round(time.perf_counter()-start,1),response.get('mode'),[(t['tool'],t['status']) for t in response.get('tools',[])],flush=True)
    results['status']='complete';OUT.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':main()
