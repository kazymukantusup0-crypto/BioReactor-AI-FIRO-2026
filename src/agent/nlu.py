"""Multilingual unit grammar + context-aware followups, independently of an LLM."""
import json
import re
from src.agent.context import extract_explicit,validate_context,NUMBERS,TEXT
from src.agent.dialogue_types import DialogueState,Entity,Extraction

NUMBER=r'-?\d+(?:[ \u00a0\u202f]\d{3})*(?:[.,]\d+)?'
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
    'temperature_recommendation':r'температур|градус|temperature|degrees?|\b\d+[.,]?\d*\s*°\s*c',
    'methane_yield':r'(?:сколько|рассчита\w*|расч[её]т|оцени\w*).*?(?:метан|биогаз|энерги)|выход|получ\w*.*метан|\bbmp\b|бмп|methane|how\s+much\s+(?:gas|biogas)|қанша\s+(?:метан|биогаз)',
    'process_guidance':r'переработ|сбраж|режим|услови|\bph\b|удерж|нагруз|снизил|digest|retention|loading|process|concentration|dilution|volatile\s+solids|өңде|қышқыл',
    'model_info':r'точност|\bmae\b|\brmse\b|r²|accuracy|model.*limit|модел.*огранич|дәлдік|үлгі.*шекте',
    'price_history':r'истори\w*\s+цен|динамик\w*\s+цен|price\s+history|баға.*тарих',
    'market_prices':r'цен[ауы]|тариф|рыноч|market\s+price|tariff|баға',
    'reactor_status':r'статус.*(?:датчик|реактор)|состояни.*датчик|sensor\s+status|reactor\s+status|датчик.*күй',
    'sources':r'источник|публикац|source|publication|дереккөз',
}


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
    cattle_slurry=re.search(r'\b(?:cattle|cow)\s+slurry\b',text,re.I)
    if cattle_slurry:return 'cattle_manure',cattle_slurry.group()
    found=[]
    for name,patterns in MATERIALS.items():
        if name in {'cattle_manure','swine_manure','poultry_manure'} and not re.search(r'навоз|manure|dung|көң|пом[её]т|litter',text,re.I) and state.value('material') not in {'manure','cattle_manure','swine_manure','poultry_manure'}:continue
        for pattern in patterns:
            for match in re.finditer(pattern,text,re.I):
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
        name=hit['material']
        if name in known or name=='manure' and any(n.endswith('_manure') for n in known):continue
        if re.search(r'(?:не|not)\s*$',text[max(0,hit['start']-8):hit['start']],re.I):continue
        found.append((hit['start'],name,text[hit['start']:hit['end']]));known.add(name)
    unique={name for _,name,_ in found}
    if len(unique)>1:
        if re.search(r'нет|не\s+.*а\s+|instead|rather|емес',text,re.I):return sorted(found)[-1][1:]
        return 'mixture',text
    if found:return sorted(found)[-1][1:]
    if re.search(r'навоз|\bmanure\b|көң',text,re.I):return 'manure',text
    return None,None


def extract(text,state=None):
    state=state or DialogueState()
    if not isinstance(text,str) or not text.strip() or len(text)>12000:raise ValueError('Message must contain 1..12000 characters')
    lang=language_of(text,state.language);entities=[]
    assumed=bool(re.search(r'предположим|допустим|например|условн\w*\s+сценар|\bassume\b|hypothetical|for\s+example|мысалы|болжам\s+ретінде',text,re.I))
    provenance='ASSUMED_FOR_SCENARIO' if assumed else 'USER_CONFIRMED'
    def add(name,value,evidence,unit=None):
        if name=='material' and value=='manure_unspecified':value='manure'
        entities.append(Entity(name=name,value=value,unit=unit,evidence=evidence,provenance=provenance))
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
                form_span=re.search(r'сух\w*|\bdry\b|подстил\w*|\bbedded\b|полужид\w*|semiliquid|жидк\w*|\bslurry\b|\bliquid\b|тв[её]рд\w*|\bsolid\b|свеж\w*|\bfresh\b|компост\w*|перегно\w*|\bcompost\w*|\bcomposted\b|перепрев\w*|rotted|хранив\w*|\bstored\b',text,re.I)
                material_at=text.casefold().find(evidence.casefold())
                if form_span and material_at>=0 and abs(form_span.start()-material_at)<=80 and not re.search(r'(?:dry|сух\w*)\s+(?:gas|газ)',text,re.I):
                    physical=axes.get('physical_state')
                    state_map={'dry':'dry','bedded':'bedded','semiliquid':'semiliquid','liquid':'slurry','solid':'fresh_solid'}
                    state_value='compost' if axes.get('decay_state')=='composted' else state_map.get(physical)
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
            capacity_context=bool(re.search(r'реактор|reactor|digester|рабоч.*объ[её]м|working\s+volume',before,re.I) and not re.search(r'получ|произв[её]л|produced|yielded|\bдал\b',before,re.I))
            gas_before=re.search(r'метан|methane|ch4|биогаз|biogas|газ[а]?',before[-18:])
            gas_after=re.match(r'\s*(?:метан|methane|ch4|биогаз|biogas)',after)
            if unit in {'L','m3'} and (gas_before or gas_after) and not capacity_context and not re.search(r'навоз|сырь|отход|manure|көң',before) and not re.search(r'(?:из|from)\s*$',before,re.I):
                nearest=list(re.finditer(r'метан|methane|ch4|биогаз|biogas|газ',before[-18:],re.I))
                subject=gas_after.group() if gas_after else nearest[-1].group()
                add('reported_methane_volume_m3' if re.search(r'метан|methane|ch4',subject,re.I) else 'reported_biogas_volume_m3',value*(.001 if unit=='L' else 1),match.group(),'m3');continue
            local_before=re.split(r'[,;!?]|\.(?!\d)',before)[-1]
            tank=bool(re.search(r'реактор|reactor|digest[eo]r|рабоч\w*\s+объ[её]м|working\s+volume|жұмыс.*көлем',local_before) or re.match(r'\s*(?:реактор|reactor)',after))
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
            tank=bool(re.search(r'\u0440\u0435\u0430\u043a\u0442\u043e\u0440|reactor|digester|working volume|\u0440\u0430\u0431\u043e\u0447\w*\s+\u043e\u0431\u044a[\u0435\u0451]\u043c',re.split(r'[,;!?]',before)[-1],re.I))
            if any(hit['start']<=2 for hit in substrate_matches(after)):tank=False
            if tank:
                if unit!='L':raise ValueError('Reactor capacity requires a volume unit')
                key='reactor_working_volume_l' if re.search(r'working|\u0440\u0430\u0431\u043e\u0447',before) else 'reactor_total_volume_l'
                add(key,value,evidence,'L');continue
            add('quantity',value,evidence,unit);add('unit',unit,evidence)
        bmp=re.search(r'(?<![\w.])('+NUMBER+r')\s*(?:mL|milliliters?)\s*(?:CH\s*4|methane)\s*(?:/|per)\s*g\s*(?:VS|volatile\s+solids)\b',text,re.I)
        if bmp:
            add('bmp_ml_ch4_g_vs',numeric(bmp.group(1),lang),bmp.group(),'mL CH4/g VS')
            add('bmp_unit','mL CH4/g VS',bmp.group())
        gas_basis=re.search(r'('+NUMBER+r')\s*K\s*[,;]\s*('+NUMBER+r')\s*bar\b',text,re.I)
        if gas_basis and re.search(r'gas\s+basis|volume\s+basis|273\.2\s*K|273\.15\s*K',text,re.I):
            temperature=numeric(gas_basis.group(1),lang);pressure=numeric(gas_basis.group(2),lang)
            add('gas_volume_basis',f'{temperature:g} K; {pressure:g} bar; moisture not specified',gas_basis.group())
        temperature=re.search(r'(?:температур\w*|temperature|температура)\s*(?:[=:]|is|равна|будет)?\s*('+NUMBER+r')|('+NUMBER+r')\s*(?:°\s*[cсC]|градус\w*|degrees?)',text,re.I)
        if temperature:add('temperature_c',numeric(next(v for v in temperature.groups() if v is not None),lang),temperature.group(),'°C')
        density=re.search(r'(?:плотност\w*|density|тығыздық)\s*(?:[=:]|is)?\s*('+NUMBER+r')\s*(?:кг\s*/\s*л|kg\s*/\s*l)',text,re.I)
        if density:add('density_kg_l',numeric(density.group(1),lang),density.group(),'kg/L')
        for key,pattern in [('ts_percent',r'\bTS\s*[=:]?\s*('+NUMBER+r')\s*%'),('vs_percent',r'\bVS\s*[=:]?\s*('+NUMBER+r')\s*%')]:
            match=re.search(pattern,text,re.I)
            if match:add(key,numeric(match.group(1),lang),match.group(),'%')
        if re.search(r'VS\s*[=:]?\s*'+NUMBER+r'\s*%\s*(?:от|of|on)\s*(?:TS|dry)',text,re.I):add('vs_basis','TS',text)
        elif re.search(r'VS\s*[=:]?\s*'+NUMBER+r'\s*%\s*(?:от\s+влажн|of\s+(?:wet|fresh))',text,re.I):add('vs_basis','fresh_mass',text)
        price=re.search(r'(?:за|for|price\s*(?:is)?|цен[ауы]\s*(?:[=:]|составляет)?|продам|предлагают|offer\s+is|бағасы)\s*('+NUMBER+r')\s*(тенге|теңге|₸|kzt|dollars?|usd|руб\w*|rub)',text,re.I)
        if price:
            add('sale_offer_amount',numeric(price.group(1),lang),price.group(0))
            currency='KZT' if re.search(r'тенге|теңге|₸|kzt',price.group(2),re.I) else 'USD' if re.search(r'usd|dollar',price.group(2),re.I) else 'RUB'
            add('sale_offer_currency',currency,price.group())
        pending=state.pending_question.id if state.pending_question else None
        if re.search(r'весь\s+(?:объ[её]м|парти)|всю\s+парти|целую\s+парти|whole\s+batch|entire\s+(?:batch|volume)|бүкіл\s+көлем|барлық\s+көлем',text,re.I) or pending=='sale_scope' and re.fullmatch(r'\s*(?:да|yes|иә)[.!]?\s*',text,re.I):add('sale_offer_scope','batch',text)
        elif re.search(r'(?:за|per)\s*(?:1\s*)?(?:кг|kg|килограмм)|килограмм\s+үшін',text,re.I):add('sale_offer_scope','kg',text)
        elif re.search(r'(?:за|per)\s*(?:1\s*)?(?:литр|litre|liter|л\b)|литр\s+үшін',text,re.I):add('sale_offer_scope','L',text)
        elif re.search(r'(?:за|per)\s*(?:1\s*)?(?:тонн|tonne|ton\b)',text,re.I):add('sale_offer_scope','t',text)
        if re.search(r'периодическ|порционн|\bbatch\b',text,re.I):add('operating_mode','batch',text)
        elif re.search(r'непрерыв|continuous|үздіксіз',text,re.I):add('operating_mode','continuous',text)
    intent_text=re.sub(r'\b[A-Za-z_][A-Za-z_0-9]*\s*=\s*(?:"[^"\n]*"|\'[^\'\n]*\'|[^\s;]+)','',text)
    intents=[name for name,pattern in INTENTS.items() if re.search(pattern,intent_text,re.I)]
    if 'model_info' in intents:intents=[i for i in intents if i!='methane_yield']
    if 'price_history' in intents:intents=[i for i in intents if i!='market_prices']
    if 'temperature_recommendation' in intents and 'methane_yield' in intents and not re.search(r'сколько|выход|объ[её]м.*метан|how\s+much|yield|қанша|\bbmp\b',text,re.I):intents.remove('methane_yield')
    if re.search(r'привет|hello|сәлем',text,re.I) and not intents:intents=['greeting']
    # General processing words do not force an extra recommendation tool in economics.
    if any(i in intents for i in ['economic_comparison','temperature_recommendation','methane_yield']):intents=[i for i in intents if i!='process_guidance']
    if not intents and any(e.name in {'reactor_total_volume_l','reactor_working_volume_l'} for e in entities):intents=['process_guidance']
    return Extraction(language=lang,intents=intents,entities=entities,
        correction=bool(re.search(r'нет[,!]?|не\s+.*\s+а\s+|исправ|поправ|instead|actually|емес',text,re.I)),
        new_batch=bool(re.search(r'новая\s+партия|другая\s+партия|new\s+batch|жаңа\s+партия',text,re.I)))
