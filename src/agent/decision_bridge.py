"""Grounded multilingual settings; hypotheses live outside confirmed batch facts."""
import copy,json,re
from src.economics.decision_schemas import DecisionInputs
from src.agent.dialogue_types import Question

def propose(text,state,new_batch=False):
    data={} if new_batch else copy.deepcopy(state.decision_settings)
    if text.lstrip().startswith('{'):
        raw=json.loads(text).get('decision_inputs')
        if raw is not None:
            if not isinstance(raw,dict):raise ValueError('decision_inputs requires an object')
            for key,value in raw.items():
                if key in {'reactor','costs','quotes','price_ids'} and isinstance(value,dict):data[key]={**data.get(key,{}),**value}
                else:data[key]=value
    else:
        options=[('chp',r'\bchp\b|когенерац|тепло\s+и\s+электр|heat\s+and\s+(?:power|electric)|жылу\s+мен\s+электр'),
                 ('sell_gas',r'прода\w*.{0,15}газ|sell.{0,10}(?:bio)?gas|газ.{0,10}сат'),
                 ('electricity',r'электрич|электроэнерг|\belectricity\b|\bpower\b|электр\s+энерг'),
                 ('heat',r'отоплен|обогрев|\bheat(?:ing)?\b|жылыту|\bжылу\b')]
        purpose_context=bool(re.search(r'для|\bfor\b|хочу|планиру|использ|үшін',text,re.I)) or len(text.split())<=7 and not re.search(r'КПД|efficiency|ПӘК|%',text,re.I)
        for value,pattern in options:
            match=re.search(pattern,text,re.I)
            if match and purpose_context and not re.search(r'не\s+$|not\s+$',text[:match.start()],re.I):data['gas_use']=value;break
        # Parameter percentages must be literal. No LLM number enters this path.
        prefixes={'recovery_fraction':r'(?:извлечени\w*|recovery|алу\s+үлесі)',
                  'thermal_efficiency':r'(?:теплов\w*\s+КПД|КПД\s+тепла|thermal\s+efficiency|жылулық\s+ПӘК)',
                  'electrical_efficiency':r'(?:электрическ\w*\s+КПД|КПД\s+электричества|electrical\s+efficiency|электрлік\s+ПӘК)',
                  'methane_fraction':r'(?:доля\s+метана|метан\w*\s+доля|methane\s+fraction|метан\s+үлесі)'}
        hypothetical=bool(re.search(r'допустим|предполож|условн|\bassum|\bif\b|мысалы|болжам',text,re.I))
        heat_energy=re.search(r'(\d+(?:[.,]\d+)?)\s*(?:кВт\s*[·*.-]?\s*ч|kwh)',text,re.I)
        if heat_energy and (state.pending_question and state.pending_question.id=='heating-kwh' or re.search(r'нагрев|подогрев|heating',text,re.I)):
            reactor=data.setdefault('reactor',{})
            reactor['auxiliary_energy_kwh']=float(heat_energy[1].replace(',','.'))
            # A measured energy quantity alone does not assert full-batch scope,
            # duration, efficiency or completeness of the entire energy balance.
        cost_labels={'preparation':r'подготовк\w*|preparation','maintenance':r'обслуживани\w*|maintenance',
            'storage':r'хранени\w*|storage','transport':r'транспорт\w*|transport',
            'gas_cleaning':r'очистк\w*\s+газа|gas cleaning','digestate_handling':r'обращени\w*\s+с\s+дигестатом|digestate handling',
            'packaging':r'упаковк\w*|packaging'}
        for key,label in cost_labels.items():
            match=re.search(r'(?:'+label+r')\s*[:=—-]?\s*(\d+(?:[.,]\d+)?)\s*(?:тенге|KZT|тг)',text,re.I)
            if match:
                amount=float(match[1].replace(',','.'))
                data.setdefault('costs',{})[key]={'low':amount,'high':amount,'provenance':'HYPOTHETICAL_SCENARIO' if hypothetical else 'USER_REPORTED','evidence':match.group()+'; batch scope to be confirmed'}
        for key,label in {'inoculum_volume_l':r'инокул[юя]м\w*','headspace_l':r'газов\w*\s+пространств\w*','resident_liquid_volume_l':r'остаток\s+(?:жидкости|в реакторе)'}.items():
            match=re.search(r'(?:'+label+r')\s*[:=—-]?\s*(\d+(?:[.,]\d+)?)\s*(?:л\b|литр\w*)',text,re.I)
            if match:data.setdefault('reactor',{})[key]=float(match[1].replace(',','.'))
        if re.search(r'периодическ\w*\s+(?:режим|партия|загрузк)|\bbatch\b|вс[её]\s+сразу',text,re.I):data.setdefault('reactor',{})['operating_mode']='batch'
        elif re.search(r'непрерывн\w*\s+(?:режим|загрузк)|\bcontinuous\b',text,re.I):data.setdefault('reactor',{})['operating_mode']='continuous'
        for key,prefix in prefixes.items():
            match=re.search(prefix+r'\s*[:=—-]?\s*(\d+(?:[.,]\d+)?)\s*%',text,re.I)
            if match:
                value=float(match[1].replace(',','.'))/100
                data[key]={'low':value,'high':value,'provenance':'HYPOTHETICAL_SCENARIO' if hypothetical else 'USER_REPORTED','evidence':match.group()}
    return DecisionInputs.model_validate(data).model_dump(mode='json',exclude_none=True)

def next_question(state,data,result):
    a=result.get('decision_analysis',{});language=state.language
    def q(identifier,ru,en,kk,options,fields):return Question(id=identifier,text={'ru':ru,'en':en,'kk':kk}[language],options=options,fields=fields,reason='Most useful next decision input')
    if data['material_state']=='unknown' and 'material_state' not in state.decision_unavailable:
        return q('research-material-form','Какой это навоз: навозная жижа, твёрдый с подстилкой, сухой или перегной?','Is it cattle slurry, bedded solid manure, dry manure or compost?','Бұл сұйық көң, төсенішті қатты көң, құрғақ көң әлде компост па?',{'ru':['Навозная жижа','Твёрдый навоз с подстилкой','Сухой навоз','Перегной'],'en':['Cattle slurry','Bedded solid manure','Dry manure','Compost'],'kk':['Сұйық көң','Төсенішті көң','Құрғақ көң','Компост']}[language],['material_state'])
    if state.decision_settings.get('gas_use','unknown')=='unknown' and 'gas_use' not in state.decision_unavailable:
        return q('decision-gas-use','Для чего планируете использовать газ?','How do you plan to use the gas?','Газды не үшін пайдаланбақсыз?',{'ru':['Для отопления','Для электричества','Тепло и электричество (CHP)'],'en':['For heating','For electricity','Heat and electricity (CHP)'],'kk':['Жылыту үшін','Электр энергиясы үшін','Жылу мен электр (CHP)']}[language],['gas_use'])
    if a.get('feasibility',{}).get('working_volume_l') is None and 'reactor_working_volume_l' not in state.decision_unavailable:
        return q('decision-working-volume','Какой рабочий объём реактора подтверждён, отдельно от полных 200 л?' if state.value('reactor_total_volume_l')==200 else 'Какой рабочий объём реактора подтверждён?','What working liquid volume is confirmed, separately from total capacity?','Реактордың толық көлемінен бөлек, расталған жұмыс көлемі қандай?',[],['reactor_working_volume_l'])
    return None
