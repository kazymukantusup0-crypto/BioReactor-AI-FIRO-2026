"""Multilingual unit grammar + context-aware followups, independently of an LLM."""
import json
import re
from src.agent.context import extract_explicit,validate_context,NUMBERS,TEXT
from src.agent.dialogue_types import DialogueState,Entity,Extraction

NUMBER=r'-?\d+(?:[ \u00a0\u202f]\d{3})*(?:[.,]\d+)?'

def temperature_alternatives(text):
    if not re.search(r'сравн|compare|салыстыр',text,re.I):return []
    values=list(dict.fromkeys(float(v.replace(',','.')) for v in re.findall(r'(-?\d+(?:[.,]\d+)?)\s*°\s*[cс]',text,re.I)))
    return values if len(values)>1 else []


def augment_requested_tasks(extraction,proposal,text):
    """Accept model task semantics with topic anchors; never accept new numbers.

    Literal grammar remains available without a model. A model may complete a
    coordinated task list that grammar only partly understood, without turning
    pure conceptual questions or background facts into batch calculations.
    """
    if not proposal:return extraction
    kinds=set(extraction.request_kinds)
    if 'scientific_explanation' in kinds and not kinds.intersection({'reactor_management','substrate_assessment','economic_comparison'}):return extraction
    anchors={'methane_yield':r'метан|газ|methane|biogas|\bbmp\b',
             'temperature_recommendation':r'температур|подогрев|нагрев|мезофил|термофил|холод|т[её]пл|°\s*[cс]|temperature|thermal|heating',
             'economic_comparison':r'выгод|эконом|прибыл|стоим|тариф|цена|целесообраз|рентаб|смысл|profit|economic|cost|price|тиімді|пайда'}
    for intent in proposal.intents:
        if intent not in anchors or not re.search(anchors[intent],text,re.I):continue
        if intent not in extraction.intents:extraction.intents.append(intent)
        kind={'temperature_recommendation':'reactor_management','economic_comparison':'economic_comparison'}.get(intent)
        if kind and kind not in extraction.request_kinds:extraction.request_kinds.append(kind)
    return extraction
# Require the Russian price stem to begin at a word boundary. Without the
# left boundary, "цен[ауы]" also matches inside "сценарий".
RU_PRICE_WORD=r'(?<![а-яё])цен[а-яё]*'
MATERIALS={
    'cattle_manure':[r'коров\w*',r'навоз\w*(?:\s+жиж\w*)?\s+крс',r'cattle\s+manure',r'cow\s+(?:dung|manure)',r'сиыр\w*'],
    'swine_manure':[r'свин\w*',r'(?:pig|swine)\s+(?:dung|manure)',r'шошқа\w*'],
    'poultry_manure':[r'птич\w*',r'курин\w*\s+пом[её]т\w*',r'(?:poultry|chicken)\s+(?:litter|manure)',r'құс\s+көң\w*'],
    'food_waste':[r'пищев\w*\s+отход\w*',r'food[ _]+waste',r'(?:тағам|тамақ)\s+қалдық\w*'],
    'chernozem':[r'черноз[её]м\w*',r'chernozem',r'black\s+soil',r'қара\s*топырақ',r'почв\w*',r'\bsoil\b'],
    'Wheat straw':[r'пшенич\w*\s+солом\w*',r'wheat\s+straw',r'бидай\s+сабан\w*'],
    'Whey':[r'сыворот\w*',r'whey',r'сарысу'],
    'Cellulose':[r'целлюлоз\w*',r'cellulose'],
    'Bird feed':[r'корм\w*\s+для\s+птиц\w*',r'bird\s+feed'],
    'Rabbit feed':[r'корм\w*\s+для\s+кролик\w*',r'rabbit\s+feed'],
    'Sunflower seeds':[r'сем\w*\s+подсолнечник\w*',r'sunflower\s+seeds'],
}
INTENTS={
    'economic_comparison':r'выгод|денег|заработ|продать|продаж|прода[мтю]|прибыл|эконом|sell|profit|cost.benefit|digest\s+it|сатқан|сату|тиімді|пайда',
    'digestate_management':r'(?:дигестат\w*|digestate).{0,120}(?:удобр\w*|npk|цен\w*|стоим\w*|прод\w*|состав\w*|разреш\w*|nutrient|fertili[sz]\w*|price|sell)|(?:удобр\w*|npk|nutrient|fertili[sz]\w*).{0,120}(?:дигестат\w*|digestate)',
    'temperature_recommendation':r'(?:какую|какая|целев\w*|рекомендуем\w*|оптимальн\w*|до\s+какой)\s+(?:рабоч\w*\s+)?температур\w*|(?:what|which)\s+temperature\b|қандай\s+температур\w*|температура\s+(?:керек|қажет)\b|(?:стоит\s+ли|нужно\s+ли|следует\s+ли)\s+(?:повыш\w*|пониж\w*|измен\w*)\s+температур\w*|(?:temperature\s+(?:should|to\s+set|setpoint|recommend)|should\s+i\s+(?:raise|lower|change)\s+the\s+temperature|recommended\s+temperature)|температур\w*.{0,35}(?:повыс|пониз|измен|установ|выстав|нормальн|оптимальн)',
    'methane_yield':r'(?:сколько|рассчита\w*|расч[её]т|оцени\w*|estimate|calculate).*?(?:метан|биогаз|энерги)|получ\w*.*метан|how\s+much\s+(?:methane|gas|biogas)|(?:bmp|бмп).{0,35}(?:потенциал\w*|potential)|(?:потенциал\w*|potential)\s+(?:метан\w*|methane)|қанша\s+(?:метан|биогаз)',
    'process_guidance':r'переработ|сбраж|режим|услови|\bph\b|удерж|нагруз|снизил|digest|retention|loading|process|concentration|dilution|volatile\s+solids|өңде|қышқыл',
    'model_info':r'точност|\bmae\b|\brmse\b|r²|accuracy|model.{0,24}(?:limit|evaluat|metric|performance)|(?:evaluat|metric|performance).{0,24}model|модел\w*.{0,20}(?:оценк|метрик|огранич)|(?:оценк|метрик).{0,20}модел|дәлдік|үлгі.*шекте',
    'price_history':r'истори\w*\s+цен|динамик\w*\s+цен|price\s+history|баға.*тарих',
    'market_prices':RU_PRICE_WORD+r'|тариф|рыноч|market\s+price|tariff|баға',
    'reactor_status':r'статус.*(?:датчик|реактор)|состояни.*датчик|sensor\s+status|reactor\s+status|датчик.*күй',
    'sources':r'источник|публикац|source|publication|дереккөз',
}

SCIENCE_TERMS=(r'\bbmp\b|\bбмп\b|\bts\b|\bvs\b|volatile\s+solids|total\s+solids|'
    r'кислород\w*.{0,80}(?:метаноген|сбраж|анаэроб)|(?:метаноген|сбраж|анаэроб).{0,80}кислород|oxygen.{0,80}(?:methanogen|anaerobic|digestion)|(?:methanogen|anaerobic|digestion).{0,80}oxygen|'
    r'\bhrt\b|hydraulic\s+retention|hydraulic\s+residence|batch\s+(?:test|experiment|assay)|'
    r'temperature.{0,50}(?:anaerobic|digestion|digester)|(?:anaerobic|digestion|digester).{0,50}temperature|'
    r'температур\w*.{0,60}(?:анаэробн\w*|сбраж|метаноген)|(?:анаэробн\w*|сбраж).{0,60}температур\w*|'
    r'reactor\s+capacity|vessel\s+capacity|(?:reactor|vessel)\s+volume|working\s+volume|'
    r'лабораторн\w*.{0,30}метан|фактическ\w*.{0,25}выход|реактор\w*.{0,30}объ[её]м|'
    r'объ[её]м\w*.{0,30}реактор|сух\w*\s+(?:веществ\w*|остат\w*)|летуч\w*\s+(?:веществ\w*|тверд\w*)')
SCIENCE_QUESTION=(r'нужен\s+ли|требуется\s+ли|is\s+oxygen\s+required|does\s+.{1,50}\s+require|что\s+такое|чем\s+.{1,80}\s+отлич\w*|в\s+ч[её]м\s+разниц\w*|'
    r'почему|как\s+.{1,100}\s+(?:влияет|работает|связан\w*)|'
    r'what\s+is|what\s+are|what\s+does|define|explain|difference\s+between|how\s+does|why\b|'
    r'\b(?:bmp|hrt|ts)\s+vs\.?\b|\bvs\.?\s+(?:actual|measured|reactor|batch|test|duration)\b|versus|'
    r'анықтам\w*|айырмашыл\w*|неге|қалай\s+.{1,100}(?:әсер|жұмыс|байланыс)')
UNCERTAINTY_QUESTION=(r'неопредел[её]нност|достоверност|насколько\s+(?:точ|над[её]ж)|'
    r'ошибк\w*\s+(?:прогноз|оценк)|насколько\s+можно\s+довер|uncertaint|reliab|'
    r'confidence\s+(?:interval|of)|prediction\s+(?:error|interval)|қаншалықты\s+(?:дәл|сенімді)')
REACTOR_ACTION=(r'стоит\s+ли|нужно\s+ли|следует\s+ли|рекомендуй|какую\s+температур|(?:what|which)\s+temperature|қандай\s+температур|температура\s+(?:керек|қажет)|'
    r'повыш\w*|пониж\w*|измен\w*|установ\w*|задать\s+температур|should\s+i|recommend|'
    r'set\s+the\s+temperature|raise\s+the\s+temperature|lower\s+the\s+temperature|increase\s+temperature|decrease\s+temperature|'
    r'загрузить|подавать|режим\s+работы|dose|setpoint')


def classify_request(text,state=None,intents=None,entities=None):
    """Classify the current turn by requested operation, independent of broad topic words."""
    state=state or DialogueState();intents=set(intents or []);entities=entities or []
    lower=text.casefold();kinds=[]
    science_question=bool(re.search(SCIENCE_TERMS,text,re.I) and (
        re.search(SCIENCE_QUESTION,text,re.I) or re.search(UNCERTAINTY_QUESTION,text,re.I)
        or re.search(r'объясни\w*|поясни\w*|explain\b|describe\b|түсіндір',text,re.I)))
    if science_question:kinds.append('scientific_explanation')
    if re.search(UNCERTAINTY_QUESTION,text,re.I):kinds.append('uncertainty_question')
    if 'economic_comparison' in intents:kinds.append('economic_comparison')
    if 'temperature_recommendation' in intents or 'process_guidance' in intents and re.search(REACTOR_ACTION,text,re.I):
        kinds.append('reactor_management')
    entity_names={getattr(e,'name',None) for e in entities}
    explicit_calc=({'vs_mass_kg','bmp_ml_ch4_g_vs'}<=entity_names or bool(re.search(
        r'(?:\d[\d.,]*\s*(?:kg|г|g)\s*(?:VS|летуч\w*\s+веществ\w*).{0,80}(?:×|\*|x)\s*\d[\d.,]*\s*(?:m?l|мл)|'
        r'\b(?:calculate|рассчита|вычисли).{0,80}(?:формул|по\s+формул))',text,re.I)))
    if explicit_calc:kinds.append('explicit_calculation')
    material_present=any(e.name=='material' for e in entities) or state.value('material') is not None or bool(state.mixture_components or state.mixture_scenario_components)
    quantity_present=any(e.name in {'quantity','mass_kg','material_volume_l'} for e in entities) or state.value('quantity') is not None or state.value('mass_kg') is not None
    explicit_yield_request=bool(re.search(r'(?:сколько|how\s+much|қанша).{0,80}(?:метан|биогаз|methane|biogas)|(?:estimate|оцен\w*|рассчита\w*).{0,80}(?:выход|yield|потенциал)',text,re.I))
    asks_yield=bool('methane_yield' in intents or explicit_yield_request)
    if asks_yield and not explicit_calc and (not science_question or explicit_yield_request):kinds.append('substrate_assessment')
    if re.search(r'\b(?:actual|measured|actual reactor yield)\b|фактическ\w*\s+(?:выход|выработк)|измеренн\w*\s+(?:выход|выработк)',text,re.I) and asks_yield and not science_question:
        kinds.append('substrate_assessment')
    if state.pending_question and not any(k in kinds for k in ['economic_comparison','reactor_management','substrate_assessment','explicit_calculation']):
        if len(text.split())<=8 or re.search(r'^(?:да|нет|не знаю|unknown|yes|no)\b',lower):kinds.append('parameter_followup')
    correction=bool(re.search(r'исправ|поправ|не\s+\d[\d.,]*|вместо|а\s+\d|actually|instead|correct(?:ion)?|not\s+\d',text,re.I))
    if correction and (state.facts or state.assumptions or any(e.name in {'quantity','mass_kg','material_volume_l'} for e in entities)):
        kinds.append('parameter_correction')
        if set(state.intents).intersection({'methane_yield','economic_comparison'}) and (quantity_present or material_present):
            kinds.append('substrate_assessment')
    return list(dict.fromkeys(kinds))


_ECONOMIC_NEGATION=re.compile(
    r'\bне\s+(?:делай|делать|сделай)\s+(?:вывод|расч[её]т|оценк\w*|анализ\w*)\b'
    r'|\bне\s+(?:оценивай|рассчитывай|считай|анализируй|сравнивай)\b'
    r'|\bdo\s+not\s+(?:make|draw|reach)\s+(?:a\s+)?(?:economic\s+|profitability\s+)?(?:conclusion|assessment|calculation)\b',re.I)
_NEGATION_CONNECTOR=re.compile(r'\b(?:но|однако|but|however)\b',re.I)


def _match_is_negated(text,name,match):
    """Ignore a keyword only when it falls inside an explicit negative request."""
    start=max([text.rfind(mark,0,match.start()) for mark in '.!?;\n']+[0])
    clause=text[start:match.start()]
    if name=='economic_comparison':
        for cue in _ECONOMIC_NEGATION.finditer(clause):
            if not _NEGATION_CONNECTOR.search(clause[cue.end():]):return True
    if name in {'economic_comparison','market_prices'}:
        if re.search(r'\bбез\s+(?:(?:текущ\w*|рыночн\w*)\s+)?$',clause,re.I):return True
        if re.search(r'\bне\s+(?:учитывай|используй|ищи|запрашивай|собирай|показывай|называй|указывай)\b(?:\s+\w+){0,4}\s*$',clause,re.I):return True
    return False


def intent_requested(text,name,pattern=None):
    """Whether a current-turn keyword match requests this intent affirmatively."""
    pattern=pattern or INTENTS[name]
    matches=list(re.finditer(pattern,text,re.I))
    if name not in {'economic_comparison','market_prices'}:return bool(matches)
    return any(not _match_is_negated(text,name,match) for match in matches)


def numeric(raw,language='ru'):
    raw=re.sub(r'[ \u00a0\u202f]','',raw)
    if language=='en' and re.fullmatch(r'-?\d{1,3}(?:,\d{3})+',raw):raw=raw.replace(',','')
    return float(raw.replace(',','.'))


def language_of(text,previous='ru'):
    if text.lstrip().startswith('{'):return previous
    text=re.sub(r'\b[A-Za-z_][A-Za-z_0-9]*\s*=\s*(?:"[^"\n]*"|\'[^\'\n]*\'|[^\s;]+)','',text)
    if re.search('[әғқңөұүһі]|сиыр|шошқа|қалдық',text,re.I):return 'kk'
    if len(re.findall('[A-Za-z]',text))>len(re.findall('[А-Яа-яЁё]',text))+5:return 'en'
    if re.search('[А-Яа-яЁё]',text):return previous if previous=='kk' and len(text.split())<4 and not re.search('коров|свин|навоз|да\b|нет\b',text,re.I) else 'ru'
    return previous


def material_of(text,state):
    def excluded_reference(start):
        before=text[max(0,start-120):start]
        return bool(re.search(r'(?:не\s+смешивай|не\s+объединяй|не\s+смешивать|do\s+not\s+mix|don.t\s+mix|not\s+combine).{0,100}$',before,re.I))
    cattle_slurry=re.search(r'\b(?:cattle|cow)\s+slurry\b',text,re.I)
    if cattle_slurry:return 'cattle_manure',cattle_slurry.group()
    found=[]
    for name,patterns in MATERIALS.items():
        if name in {'cattle_manure','swine_manure','poultry_manure'} and not re.search(r'навоз|manure|dung|көң|пом[её]т|litter',text,re.I) and state.value('material') not in {'manure','cattle_manure','swine_manure','poultry_manure'}:continue
        for pattern in patterns:
            for match in re.finditer(pattern,text,re.I):
                if excluded_reference(match.start()):continue
                before=text[max(0,match.start()-8):match.start()]
                after=text[match.end():match.end()+9]
                if re.search(r'(?:не|not)\s*$',before,re.I) or re.match(r'\s*емес',after,re.I):continue
                found.append((match.start(),name,match.group()));break
    from src.advisor.catalog import matches as catalog_matches,normalized
    known=set()
    for _,name,_ in found:
        try:known.add(normalized(name))
        except ValueError:known.add(name)  # Preserve historical Hafner categories.
    for hit in catalog_matches(text):
        if excluded_reference(hit['start']):continue
        name=hit['material']
        if name in known or name=='manure' and any(n.endswith('_manure') for n in known):continue
        if re.search(r'(?:не|not)\s*$',text[max(0,hit['start']-8):hit['start']],re.I):continue
        found.append((hit['start'],name,text[hit['start']:hit['end']]));known.add(name)
    unique={name for _,name,_ in found}
    if len(unique)>1:
        if re.search(r'нет|не\s+.*а\s+|instead|rather|емес',text,re.I):return sorted(found)[-1][1:]
        return 'mixture',text
    if found:
        name=sorted(found)[-1][1]
        try:
            from src.advisor.catalog import normalized
            name=normalized(name)
        except ValueError:
            pass
        return name,sorted(found)[-1][2]
    if re.search(r'навоз|\bmanure\b|көң',text,re.I):return 'manure',text
    return None,None


def extract(text,state=None):
    state=state or DialogueState()
    if not isinstance(text,str) or not text.strip() or len(text)>12000:raise ValueError('Message must contain 1..12000 characters')
    lang=language_of(text,state.language);entities=[]
    assumed=bool(re.search(r'предположим|допустим|например|гипотетич\w*|условн\w*\s+(?:сценар|расч[её]т|пример)|\bassume\b|hypothetical|for\s+example|мысалы|болжам\s+ретінде',text,re.I))
    assumed_pattern=r'предположим|допустим|например|гипотетич\w*|условн\w*\s+(?:сценар|расч[её]т|пример)|\bassume\b|hypothetical|for\s+example|мысалы|болжам\s+ретінде'
    measured_pattern=r'измеренн\w*|измерил\w*|лабораторн\w*\s+(?:измер|определ)|measured|laboratory\s+(?:measurement|measured)'
    def provenance_for(evidence):
        if not assumed:return 'USER_CONFIRMED'
        start=text.find(evidence) if evidence else -1
        if start<0:start=0
        left=max([text.rfind(mark,0,start) for mark in ';.!?\n'])+1
        right=min([p for mark in ';.!?\n' if (p:=text.find(mark,start))>=0]+[len(text)])
        clause=text[left:right]
        if re.search(measured_pattern,clause,re.I):return 'USER_CONFIRMED'
        if re.search(assumed_pattern,clause,re.I):return 'ASSUMED_FOR_SCENARIO'
        # A leading scenario label applies to later values in the same statement,
        # unless that value has its own explicit measurement clause.
        first=min([p for mark in ';.!?\n' if (p:=text.find(mark))>=0]+[len(text)])
        preamble=text[:first]
        return 'ASSUMED_FOR_SCENARIO' if re.search(assumed_pattern,preamble,re.I) else 'USER_CONFIRMED'
    def add(name,value,evidence,unit=None):
        if name=='material' and value=='manure_unspecified':value='manure'
        entities.append(Entity(name=name,value=value,unit=unit,evidence=evidence,provenance=provenance_for(evidence)))
    if text.lstrip().startswith('{'):
        raw=json.loads(text)
        extra=set(raw)-NUMBERS-TEXT-{'substrate','units','market_scenario','quantity','unit','ts_percent','vs_percent','vs_basis','reactor_total_volume_l','reactor_working_volume_l','operating_mode','sale_offer_amount','sale_offer_scope','sale_offer_currency','process_parameters','decision_inputs','mixture_components','advisor_inputs'}
        if extra:raise ValueError('Unknown input fields: '+', '.join(sorted(extra)))
        legacy=validate_context({k:v for k,v in raw.items() if k in NUMBERS|TEXT|{'substrate','units','market_scenario'}})
        for key,value in {**raw,**legacy}.items():
            if key in {'units','substrate','process_parameters','decision_inputs','mixture_components','advisor_inputs'}:continue
            name='reactor_total_volume_l' if key=='reactor_volume_l' else key
            add(name,value,text)
        if 'quantity' not in raw:
            if 'mass_kg' in raw and not (state.value('unit') in {'L','m3'} and raw.get('material',raw.get('substrate',state.value('material')))==state.value('material')):add('quantity',raw['mass_kg'],text,'kg');add('unit','kg',text)
            elif 'material_volume_l' in raw:add('quantity',raw['material_volume_l'],text,'L');add('unit','L',text)
    else:
        material,evidence=material_of(text,state)
        if material:
            add('material',material,evidence)
            # Capture a material form stated in the same phrase. Without this,
            # a dry food-waste batch could silently inherit a prepared-pulp
            # profile simply because its preparation state was omitted.
            from src.advisor.material_axes import extract as extract_axes
            axes=extract_axes(text)
            if evidence:
                form_span=re.search(r'сух\w*|\bdry\b|подстил\w*|\bbedded\b|полужид\w*|semiliquid|жидк\w*|\bslurry\b|\bliquid\b|тв[её]рд\w*|\bsolid\b|свеж\w*|\bfresh\b|измельч\w*|\bshredded\b|компост\w*|перегно\w*|\bcompost\w*|\bcomposted\b|перепрев\w*|rotted|хранив\w*|\bstored\b',text,re.I)
                material_at=text.casefold().find(evidence.casefold())
                if form_span and material_at>=0 and abs(form_span.start()-material_at)<=80 and not re.search(r'(?:dry|сух\w*)\s+(?:gas|газ)',text,re.I):
                    physical=axes.get('physical_state')
                    state_map={'dry':'dry','bedded':'bedded','semiliquid':'semiliquid','liquid':'slurry','solid':'fresh_solid','shredded':'shredded'}
                    state_value='compost' if axes.get('decay_state')=='composted' else state_map.get(physical)
                    if state_value is None and re.search(r'измельч\w*|\bshredded\b',form_span.group(),re.I):state_value='shredded'
                    if physical:add('physical_state',physical,form_span.group())
                    if axes.get('decay_state'):add('decay_state',axes['decay_state'],form_span.group())
                    if state_value:add('material_state',state_value,form_span.group())
        # Preserve existing explicit key=value grammar and regional parsing.
        try:legacy=extract_explicit(text)
        except ValueError:
            if re.search(r'\b[A-Za-z_]+\s*=',text):raise
            legacy={}
        explicit_fields=set(re.findall(r'\b([A-Za-z_][A-Za-z_0-9]*)\s*=',text))
        for key,value in legacy.items():
            if key in explicit_fields:
                name='reactor_total_volume_l' if key=='reactor_volume_l' else key
                if key in {'gas_volume_basis','price_gas_volume_basis'}:value=value.rstrip('.,;!?')
                add(name,value,text)
                if key=='mass_kg' and state.value('unit') not in {'L','m3'}:add('quantity',value,text,'kg');add('unit','kg',text)
                elif key=='material_volume_l' and state.value('quantity') is None:add('quantity',value,text,'L');add('unit','L',text)
                continue
            if key=='material' and re.search(r'\b(?:material|substrate)\s*=',text):
                add('material',value,text);continue
            if key in {'material','material_volume_l','reactor_volume_l','mass_kg','temperature_c'}:continue
            add(key,value,text)
        unit_pattern=r'кубическ\w*\s+метр\w*|cubic\s+met(?:re|er)s?|m\^?3|м[³3]|литр\w*|lit(?:re|er)s?|\bL\b|л\b|тонн\w*|tonnes?|tons?|т\b|килограмм\w*|kilograms?|кг\b|kg\b|грамм\w*|grams?|г\b|g\b'
        for match in re.finditer(r'('+NUMBER+r')\s*('+unit_pattern+r')',text,re.I):
            value=numeric(match.group(1),lang);unit_raw=match.group(2).casefold()
            unit='m3' if re.search(r'куб|cubic|m\^?3|м[³3]',unit_raw) else 'L' if re.match(r'лит|lit|л$|l$',unit_raw) else 't' if re.match(r'тон|ton|т$',unit_raw) else 'kg' if re.match(r'кг|kg|кило|kilo',unit_raw) else 'g'
            before=text[max(0,match.start()-50):match.start()].casefold();after=text[match.end():match.end()+25].casefold()
            prior_quantity=state.value('quantity');prior_unit=state.value('unit')
            reference_only=bool(re.search(r'(?:не\s+(?:заменяя|замени|заменяй|меняя|меняй|изменяя|перезаписывая)|без\s+замены|without\s+replacing|do\s+not\s+replace|don.t\s+replace|keep\s+(?:the\s+)?(?:confirmed\s+)?(?:recorded\s+)?(?:mass|value))(?:(?![.!?;]).){0,100}$',before,re.I))
            mass_factor={'kg':1,'t':1000,'g':.001};volume_factor={'L':1,'m3':1000}
            if reference_only and prior_quantity is not None and prior_unit in mass_factor|volume_factor and unit in mass_factor|volume_factor:
                prior_family='mass' if prior_unit in mass_factor else 'volume';current_family='mass' if unit in mass_factor else 'volume'
                prior_value=prior_quantity*(mass_factor[prior_unit] if prior_family=='mass' else volume_factor[prior_unit])
                current_value=value*(mass_factor[unit] if current_family=='mass' else volume_factor[unit])
                if prior_family==current_family and abs(prior_value-current_value)<=max(1e-9,abs(prior_value)*1e-9):continue
            water_after=bool(re.match(r'\s*(?:of\s+)?(?:clean\s+|чист\w*\s+)?(?:water\b|вод[аыу]\b)',after,re.I))
            water_before=bool(re.search(r'(?:water|dilution\s+water|вод[аыу])\s*[:=]?\s*$',before,re.I))
            if water_after or water_before:
                if unit in {'L','m3'}:add('dilution_water_l',value*(1000 if unit=='m3' else 1),match.group(),'L')
                continue
            if re.match(r'\s*(?:CH\s*4|methane)\s*(?:/|per)\s*g\s*(?:VS|volatile\s+solids)\b',after,re.I):continue
            if unit in {'kg','g','t'} and re.match(r'\s*(?:measured\s+)?(?:VS\b|volatile\s+solids\b)',after,re.I):
                add('vs_mass_kg',value*({'kg':1,'g':.001,'t':1000}[unit]),match.group(),'kg VS');continue
            if unit in {'kg','g','t'} and re.search(r'(?:\bVS|volatile\s+solids)(?:\s+mass)?\s*(?:is|of|=|:)?\s*$',before,re.I):
                add('vs_mass_kg',value*({'kg':1,'g':.001,'t':1000}[unit]),match.group(),'kg VS');continue
            if re.search(r'(?:\bVS|volatile\s+solids|летуч\w*(?:\s+\w+){0,3})(?:\s+(?:mass|масса|составляет|равна))?\s*[=:]?\s*$',before,re.I) and unit in {'kg','g','t'}:
                add('vs_mass_kg',value*({'kg':1,'g':.001,'t':1000}[unit]),match.group(),'kg VS');continue
            if unit in {'kg','g','t'} and state.value('unit') in {'L','m3'} and re.search(r'масс|вес|взвес|weigh|mass|салмақ',before):
                add('mass_kg',value*({'kg':1,'g':.001,'t':1000}[unit]),match.group(),'kg');continue
            if re.search(r'(?:плотност|density|тығыздық)\w*\s*(?:[=:]|is)?\s*$',before):continue
            capacity_context=bool(re.search(r'реактор|reactor|digester|сосуд|ёмкост|емкост|бак|vessel|tank|container|рабоч.*объ[её]м|working\s+volume',before,re.I) and not re.search(r'получ|произв[её]л|produced|yielded|\bдал\b',before,re.I))
            gas_before=re.search(r'метан|methane|ch\s*[₄4]|биогаз|biogas|газ[а]?',before[-30:])
            gas_after=re.match(r'\s*(?:(?:сыр\w*|raw)\s+)?(?:метан|methane|ch\s*[₄4]|биогаз|biogas)',after)
            if unit in {'L','m3'} and (gas_before or gas_after) and not capacity_context and not re.search(r'навоз|сырь|отход|manure|көң',before) and not re.search(r'(?:из|from)\s*$',before,re.I):
                nearest=list(re.finditer(r'метан|methane|ch4|биогаз|biogas|газ',before[-18:],re.I))
                subject=gas_after.group() if gas_after else nearest[-1].group()
                add('reported_methane_volume_m3' if re.search(r'метан|methane|ch\s*[₄4]',subject,re.I) else 'reported_biogas_volume_m3',value*(.001 if unit=='L' else 1),match.group(),'m3');continue
            local_before=re.split(r'[,;!?]|\.(?!\d)',before)[-1]
            tank=bool(re.search(r'реактор|reactor|digest[eo]r|сосуд|ёмкост|емкост|бак|vessel|tank|container|рабоч\w*\s+объ[её]м|working\s+volume|жұмыс.*көлем',local_before) or re.match(r'\s*(?:реактор|reactor|сосуд|ёмкост|емкост|бак|vessel|tank|container)',after,re.I))
            if re.match(r'\s*(?:навоз|сырь|отход|manure|көң|food)',after):tank=False
            from src.advisor.catalog import matches as substrate_matches
            if any(hit['start']<=2 for hit in substrate_matches(after)):tank=False
            from src.agent.quantity_roles import reactor_field
            role=reactor_field(text,match.start(),match.end())
            if role:
                tank=True
            if tank:
                if unit not in {'L','m3'}:raise ValueError('Reactor volume requires litres or cubic metres')
                name=role or ('reactor_working_volume_l' if re.search(r'рабоч|working|жұмыс',before) else 'reactor_total_volume_l')
                add(name,value*(1000 if unit=='m3' else 1),match.group(),'L');continue
            add('quantity',value,match.group(),unit);add('unit',unit,match.group())
        from src.agent.quantity_words import amounts as word_amounts
        from src.advisor.catalog import matches as substrate_matches
        for amount in word_amounts(text):
            value=amount['value'];unit=amount['unit'];evidence=amount['text']
            before=text[max(0,amount['start']-50):amount['start']].casefold()
            after=text[amount['end']:amount['end']+35].casefold()
            if re.match(r'\s*(?:water|\u0432\u043e\u0434[\u0430\u044b\u0443])',after) and unit=='L':
                add('dilution_water_l',value,evidence,'L');continue
            if re.match(r'\s*(?:VS\b|volatile solids)',after,re.I) and unit in {'kg','t','g'}:
                add('vs_mass_kg',value*{'kg':1,'t':1000,'g':.001}[unit],evidence,'kg VS');continue
            tank=bool(re.search(r'\u0440\u0435\u0430\u043a\u0442\u043e\u0440|reactor|digester|\u0431\u0430\u043a|working volume|\u0440\u0430\u0431\u043e\u0447\w*\s+\u043e\u0431\u044a[\u0435\u0451]\u043c',re.split(r'[,;!?]',before)[-1],re.I))
            if any(hit['start']<=2 for hit in substrate_matches(after)):tank=False
            if tank:
                if unit!='L':raise ValueError('Reactor capacity requires a volume unit')
                key='reactor_working_volume_l' if re.search(r'working|\u0440\u0430\u0431\u043e\u0447',before) else 'reactor_total_volume_l'
                add(key,value,evidence,'L');continue
            add('quantity',value,evidence,unit);add('unit',unit,evidence)
        bmp=re.search(r'(?<![\w.])('+NUMBER+r')\s*(?:mL|мл|milliliters?)\s*(?:CH\s*[₄4]|methane|метан)\s*(?:/|per)\s*(?:g|г)\s*(?:VS|volatile\s+solids)\b',text,re.I)
        if bmp:
            add('bmp_ml_ch4_g_vs',numeric(bmp.group(1),lang),bmp.group(),'mL CH4/g VS')
            add('bmp_unit','mL CH4/g VS',bmp.group())
        gas_basis=re.search(r'('+NUMBER+r')\s*K\s*[,;]\s*('+NUMBER+r')\s*bar\b',text,re.I)
        if gas_basis and re.search(r'gas\s+basis|volume\s+basis|273\.2\s*K|273\.15\s*K',text,re.I):
            temperature=numeric(gas_basis.group(1),lang);pressure=numeric(gas_basis.group(2),lang)
            add('gas_volume_basis',f'{temperature:g} K; {pressure:g} bar; moisture not specified',gas_basis.group())
        temperature=re.search(r'(?:температур\w*|temperature|температура)\s*(?:[=:]|is|равна|будет)?\s*('+NUMBER+r')|('+NUMBER+r')\s*(?:°\s*[cсC]|градус\w*|degrees?)',text,re.I)
        if temperature and not temperature_alternatives(text):add('temperature_c',numeric(next(v for v in temperature.groups() if v is not None),lang),temperature.group(),'°C')
        from src.agent.quantities9 import user_time_horizons
        horizons=user_time_horizons(text)
        if horizons:add('duration_days',horizons[-1]['value'],horizons[-1]['reference'],'day')
        mode=re.search(r'непрерывн\w*|continuous|порционн\w*|периодическ\w*|\bbatch\b',text,re.I)
        if mode:add('operating_mode','continuous' if re.search(r'непрерыв|continuous',mode.group(),re.I) else 'batch',mode.group())
        use=re.search(r'для\s+(?:отоплен\w*|обогрев\w*|электричеств\w*)|(?:for\s+)?(?:heating|electricity)',text,re.I)
        if use:add('intended_use','electricity' if re.search(r'электр|electric',use.group(),re.I) else 'heat',use.group())
        density=re.search(r'(?:плотност\w*|density|тығыздық)\s*(?:[=:]|is)?\s*('+NUMBER+r')\s*(?:кг\s*/\s*л|kg\s*/\s*l)',text,re.I)
        if density:add('density_kg_l',numeric(density.group(1),lang),density.group(),'kg/L')
        for key,pattern in [('ts_percent',r'\bTS\s*(?:(?:[=:]|равен|равна|составляет|is)\s*)?('+NUMBER+r')\s*%'),
                            ('vs_percent',r'\bVS(?:\s*/\s*TS)?\s*(?:(?:[=:]|равен|равна|составляет|is)\s*)?('+NUMBER+r')\s*%')]:
            match=re.search(pattern,text,re.I)
            if match:add(key,numeric(match.group(1),lang),match.group(),'%')
        vs_ts=re.search(r'\bVS(?:\s*/\s*TS)?\s*(?:(?:[=:]|равен|равна|составляет|is)\s*)?'+NUMBER+r'\s*%\s*(?:(?:от|of|on)\s*(?:TS|dry))?',text,re.I)
        if vs_ts and re.search(r'(?:/\s*TS|от\s*TS|of\s*TS|on\s*dry)',vs_ts.group(),re.I):add('vs_basis','TS',vs_ts.group())
        elif re.search(r'\bVS\s*(?:(?:[=:]|равен|равна|составляет|is)\s*)?'+NUMBER+r'\s*%\s*(?:от\s+влажн|of\s+(?:wet|fresh))',text,re.I):add('vs_basis','fresh_mass',text)
        price=re.search(r'(?:по|за|for|price\s*(?:is)?|'+RU_PRICE_WORD+r'\s*(?:[=:]|составляет)?|продам|предлагают|offer\s+is|бағасы)\s*('+NUMBER+r')\s*(тенге|теңге|₸|kzt|dollars?|usd|руб\w*|rub)',text,re.I)
        if price:
            add('sale_offer_amount',numeric(price.group(1),lang),price.group(0))
            currency='KZT' if re.search(r'тенге|теңге|₸|kzt',price.group(2),re.I) else 'USD' if re.search(r'usd|dollar',price.group(2),re.I) else 'RUB'
            add('sale_offer_currency',currency,price.group())
        pending=state.pending_question.id if state.pending_question else None
        if re.search(r'весь\s+(?:объ[её]м|парти)|всю\s+парти|целую\s+парти|whole\s+batch|entire\s+(?:batch|volume)|бүкіл\s+көлем|барлық\s+көлем',text,re.I) or pending=='sale_scope' and re.fullmatch(r'\s*(?:да|yes|иә)[.!]?\s*',text,re.I):add('sale_offer_scope','batch',text)
        elif re.search(r'(?:за|per)\s*(?:1\s*)?(?:кг|kg|килограмм)|килограмм\s+үшін',text,re.I):add('sale_offer_scope','kg',text)
        elif re.search(r'(?:за|per)\s*(?:1\s*)?(?:литр|litre|liter|л\b)|литр\s+үшін',text,re.I):add('sale_offer_scope','L',text)
        elif re.search(r'(?:за|per)\s*(?:1\s*)?(?:тонн|tonne|ton\b)',text,re.I):add('sale_offer_scope','t',text)
        for index,entity in enumerate(entities):
            if entity.name=='sale_offer_amount':
                currency=next((e.value for e in reversed(entities) if e.name=='sale_offer_currency'),'KZT')
                scope=next((e.value for e in reversed(entities) if e.name=='sale_offer_scope'),None)
                if scope:entities[index]=entity.model_copy(update={'unit':f'{currency}/{scope}'})
        methane_fraction=re.search(r'(?:дол\w*\s+(?:CH\s*[₄4]|метан\w*|methane)|methane\s+fraction|CH\s*[₄4]\s+fraction)\s*(?:(?:[=:]|равна|равен|составляет|is)\s*)?('+NUMBER+r')\s*%|('+NUMBER+r')\s*%\s*(?:CH\s*[₄4]|метан\w*|methane)',text,re.I)
        if methane_fraction:
            raw=next(group for group in methane_fraction.groups() if group is not None)
            add('methane_fraction',numeric(raw,lang)/100,methane_fraction.group(),'fraction')
        lhv=re.search(r'(?:\bLHV\b|lower\s+heating\s+value|низш\w*\s+теплотвор\w*|теплотворн\w*\s+способност\w*)\s*(?:[=:]|равн\w*|составля\w*|is)?\s*('+NUMBER+r')\s*(kWh|кВт[·⋅* .]?ч)\s*/\s*(?:m[³3]|м[³3]|m\^?3)',text,re.I)
        if lhv:add('heating_value_kwh_m3',numeric(lhv.group(1),lang),lhv.group(),'kWh/m3')
        efficiency=re.search(r'(?:электрическ\w*\s+КПД|КПД(?:\s+генератор\w*)?|electrical\s+efficien\w*|electricity\s+efficien\w*)\s*(?:[=:]|равен|равна|составляет|is)?\s*('+NUMBER+r')\s*%',text,re.I)
        if efficiency:add('electricity_efficiency',numeric(efficiency.group(1),lang)/100,efficiency.group(),'fraction')
        if re.search(r'периодическ|порционн|\bbatch\b',text,re.I):add('operating_mode','batch',text)
        elif re.search(r'непрерыв|continuous|үздіксіз',text,re.I):add('operating_mode','continuous',text)
    intent_text=re.sub(r'\b[A-Za-z_][A-Za-z_0-9]*\s*=\s*(?:"[^"\n]*"|\'[^\'\n]*\'|[^\s;]+)','',text)
    intents=[name for name,pattern in INTENTS.items() if intent_requested(intent_text,name,pattern)]
    request_kinds=classify_request(text,state,intents,entities)
    # Topic terms such as BMP, methane yield, and temperature can occur in an
    # educational comparison. Do not turn those terms into a batch estimate or
    # an operating recommendation unless the user also asks for that operation.
    if 'scientific_explanation' in request_kinds:
        if 'substrate_assessment' not in request_kinds:intents=[i for i in intents if i!='methane_yield']
        if 'reactor_management' not in request_kinds:intents=[i for i in intents if i not in {'temperature_recommendation','process_guidance'}]
        if 'scientific_explanation' not in intents:intents.append('scientific_explanation')
    if 'uncertainty_question' in request_kinds and 'uncertainty_question' not in intents:intents.append('uncertainty_question')
    if 'model_info' in intents:intents=[i for i in intents if i!='methane_yield']
    if 'price_history' in intents:intents=[i for i in intents if i!='market_prices']
    if 'temperature_recommendation' in intents and 'methane_yield' in intents and not re.search(r'сколько|выход|объ[её]м.*метан|how\s+much|yield|қанша|\bbmp\b',text,re.I):intents.remove('methane_yield')
    if re.search(r'привет|hello|сәлем',text,re.I) and not intents:intents=['greeting']
    profile_lookup=bool(re.search(r'каталог|профил\w*|аналог\w*|покрыти\w*|подходит\w*|подходящ\w*|\u043b\u0438\u0442\u0435\u0440\u0430\u0442\u0443\u0440\w*|\u043d\u0430\u0443\u0447\u043d\w*\s+\u0434\u0430\u043d\u043d\w*|transferability|catalog(?:ue)?|profile|analog|scientific\s+literature',text,re.I))
    if profile_lookup and 'profile_lookup' not in intents:intents.append('profile_lookup')
    if (re.search(r'тариф\w*\s+природн\w*\s+газ|natural\s+gas\s+tariff',text,re.I)
            and re.search(r'сыр\w*\s+биогаз|raw\s+biogas',text,re.I)):
        # A commodity-equivalence question is not a feedstock-yield request.
        intents=[i for i in intents if i!='methane_yield']
    # General processing words do not force an extra recommendation tool in economics.
    if any(i in intents for i in ['economic_comparison','temperature_recommendation','methane_yield']):intents=[i for i in intents if i!='process_guidance']
    if not intents and any(e.name in {'reactor_total_volume_l','reactor_working_volume_l'} for e in entities):intents=['process_guidance']
    from src.agent.batch_intent import starts_new_batch
    if temperature_alternatives(text):
        if 'temperature_recommendation' not in intents:intents.append('temperature_recommendation')
        if 'reactor_management' not in request_kinds:request_kinds.append('reactor_management')
    return Extraction(language=lang,intents=intents,entities=entities,
        request_kinds=request_kinds,
        correction=bool(re.search(r'нет[,!]?|не\s+.*\s+а\s+|исправ|поправ|instead|actually|емес',text,re.I)),
        new_batch=starts_new_batch(text))
