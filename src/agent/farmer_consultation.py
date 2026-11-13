"""Typed, multi-task consultation over existing tools; no independent calculators."""
from typing import Literal
import copy
import re
from pydantic import Field
from src.agent.dialogue_types import Strict
from src.agent.analytical import span
from src.economics.energy_conversion import scale

def public_prose(payload,results):
    """Presentation-only removal of private references, never repair of claims.

    Typed evidence_ids and the provider's raw draft stay unchanged in diagnostics.
    Numbers, negations and scientific propositions are not rewritten.
    """
    result=copy.deepcopy(payload);changed=[]
    ids=[s['id'] for s in results.get('assess_substrate_potential',{}).get('scenarios',[])]
    def clean(text):
        if not isinstance(text,str):return text
        for index,sid in enumerate(ids):
            token=r'(?<![\w])'+re.escape(sid)+r'(?![\w]|\.[A-Za-z_])'
            if not re.search(token,text):continue
            changed.append(sid)
            text=re.sub(r'\(\s*(?:(?:сценарий|вариант|scenario)\s+)?'+token+r'\s*\)','',text,flags=re.I)
            text=re.sub(r'(?:(?:сценарий|вариант|scenario)\s+)?'+token,'рассмотренный литературный вариант',text,flags=re.I)
        return re.sub(r'\s+([,.;!?])',r'\1',re.sub(r' {2,}',' ',text)).strip()
    for key in ('conclusion','explanation','next_question'):result[key]=clean(result.get(key))
    if isinstance(result.get('limitations'),list):result['limitations']=[clean(v) for v in result['limitations']]
    return result,sorted(set(changed))

class ConsultationInputs(Strict):
    substrate:str|None=None
    feedstock_volume_l:float|None=Field(default=None,gt=0)
    reactor_volume_l:float|None=Field(default=None,gt=0)
    temperature_c:float|None=None
    operating_mode:Literal['batch','continuous']|None=None
    duration_days:float|None=Field(default=None,gt=0)
    intended_use:str='unknown'
    region:str|None=None
    measured_parameters:dict=Field(default_factory=dict)
    literature_assumptions:list=Field(default_factory=list)
    components:list[dict]=Field(default_factory=list)
    tasks:list[Literal['methane','temperature','economics','risks']]=Field(default_factory=list)

def project(state,extraction,text):
    prior=state.advanced.get('farmer_consultation',{})
    from src.agent.nlu import temperature_alternatives
    alternatives=temperature_alternatives(text)
    if alternatives:state.advanced['temperature_comparison_c']=alternatives
    elif any(e.name in {'temperature_c','material'} for e in extraction.entities):state.advanced.pop('temperature_comparison_c',None)
    tasks=[task for intent,task in [('methane_yield','methane'),('temperature_recommendation','temperature'),('economic_comparison','economics')] if intent in state.intents]
    from src.recommendations.retrieval import topics_for
    if set(topics_for(text)) & {'ph','loading','co_digestion','low_gas'}:tasks.append('risks')
    def value(key):
        item=state.assumptions.get(key)
        return item.value if item is not None else state.value(key)
    changed={e.name for e in extraction.entities}
    if prior and (alternatives or changed.intersection({'temperature_c','duration_days','quantity','mass_kg','material_volume_l','market_region','intended_use','operating_mode'})) and not extraction.new_batch:
        tasks=list(dict.fromkeys(prior.get('tasks',[])+tasks))
    if not (value('material') or state.mixture_components) or not tasks:return None
    if not prior and not {'temperature','economics','risks'}.intersection(tasks):return None
    temp=state.assumptions.get('temperature_c')
    typed=ConsultationInputs(substrate=value('material'),feedstock_volume_l=value('material_volume_l'),reactor_volume_l=value('reactor_total_volume_l'),
        temperature_c=temp.value if temp else state.value('temperature_c'),duration_days=state.value('duration_days'),operating_mode=state.value('operating_mode'),
        intended_use=state.value('intended_use') or state.decision_settings.get('gas_use','unknown'),region=state.value('market_region'),
        measured_parameters={k:v.model_dump(mode='json') for k,v in state.facts.items() if k in {'density_kg_l','ts_percent','vs_percent','vs_mass_kg','bmp_ml_ch4_g_vs'}},
        components=state.mixture_scenario_components or state.mixture_components,tasks=tasks)
    state.advanced['farmer_consultation']=typed.model_dump(mode='json')
    return typed

def required_tools(inputs,state):
    tools=[] if inputs.tasks==['economics'] else ['search_scientific_sources']
    amount=any(state.value(k) is not None or k in state.assumptions for k in ['quantity','mass_kg']) or bool(state.mixture_scenario_components or state.mixture_components)
    if amount and {'methane','economics'}.intersection(inputs.tasks):tools.append('estimate_methane_yield' if inputs.feedstock_volume_l is not None else 'assess_substrate_potential')
    if 'temperature' in inputs.tasks:tools.append('assess_process_evidence')
    if amount and 'economics' in inputs.tasks:tools.append('evaluate_partial_economics')
    return tools

def temperature_options(data,studies):
    from src.research.profile_cache import read_profile
    from src.data.prepare import ROOT
    from src.economics.decision_schemas import ReactorInputs
    from src.economics.reactor_balance import calculate
    from src.agent.analytical import components
    document=read_profile(ROOT/'data/research/farmer_profiles.json')
    from src.optimizer.energy_model import SOURCES as heat_sources
    cs=components(data);materials={c.material for c in cs} or {data['facts'].get('material')};forms={c.material_state for c in cs}
    extra=[s for s in document['process_studies'] if s['material'] in materials and (not forms or 'unknown' in forms or forms.intersection(s['material_states']))]
    meso=sorted({s['temperature_c'] for s in studies if 35<=s['temperature_c']<=38}|{s['discussion_temperature_c'] for s in extra})
    discussion=meso[0] if meso else None;raw=dict(data.get('decision',{}).get('reactor',{}));current=data['facts'].get('temperature_c')
    targets=data.get('temperature_comparison_c') or list(dict.fromkeys(([current] if current is not None else [])+([discussion] if discussion is not None else [])))
    return {'discussion_temperature_c':discussion,'user_temperature_c':current,
            'options':[{'temperature_c':t,'kind':'USER_SCENARIO' if t==current else 'LITERATURE_DISCUSSION',
                        'heat_balance':calculate(ReactorInputs.model_validate({**raw,'temperature_c':t})),'operation_authorized':False} for t in targets],
            'process_studies':extra,'sources':[s for s in document['sources'] if s['id'] in {s['source_id'] for s in extra}]+heat_sources,
            'automatic_setpoint_c':None,'operation_authorized':False,
            'interpretation':'A study-based starting point for engineering discussion; not a validated setpoint or optimum.'}

def priority_question(state,results):
    f=state.value;science=results.get('assess_substrate_potential',{})
    if set(state.advanced.get('farmer_consultation',{}).get('tasks',[]))=={'temperature'} and f('temperature_c') is None:
        return 'Какая сейчас температура сырья и помещения, где стоит реактор?'
    if not (f('quantity') or f('mass_kg') or state.mixture_scenario_components or state.mixture_components):return 'Сколько сырья вы планируете перерабатывать за одну загрузку?'
    if state.analytical_mode=='alternatives' and f('physical_state') in {None,'unknown'}:return 'В каком виде доступно каждое из сравниваемых видов сырья?'
    if any(s.get('loading',{}).get('simultaneous_load_possible') is False for s in science.get('scenarios',[])):return 'Какой рабочий объём загрузки разрешён изготовителем реактора?'
    if f('physical_state') in {None,'unknown'} and f('material_state') in {None,'unknown'}:return 'Сырьё жидкое и разбавленное, плотное или содержит подстилку?'
    if 'evaluate_partial_economics' in results and not f('market_region'):return 'В каком регионе находится установка?'
    if 'assess_process_evidence' in results and f('temperature_c') is None:return 'Какая сейчас температура сырья и помещения, где стоит реактор?'
    if f('reactor_working_volume_l') is None:return 'Какой рабочий объём загрузки разрешён изготовителем реактора?'
    return 'Какой фактический расход энергии на подогрев и перемешивание за цикл?'

def synthesis_context(results,state,query,evidence):
    from src.advisor.estimation import model_context
    science=results.get('assess_substrate_potential',{})
    payload=model_context(science,query,evidence) if science.get('estimation_mode') else {'question':query,'evidence':{k:{f:v.get(f) for f in ['label','value','unit','level']} for k,v in list(evidence.items())[:4]}}
    eco=results.get('evaluate_partial_economics',{});process=results.get('assess_process_evidence',{}).get('temperature_consultation',{})
    # Cover every distinct material before spending context on repeated studies.
    science_rows=results.get('assess_substrate_potential',{}).get('scenarios',[])
    selected=[];covered=set()
    for row in science_rows:
        materials=tuple(sorted({c['material'] for c in row.get('components',[])}));key=row['id']+'.methane'
        if key in evidence and materials not in covered:selected.append(key);covered.add(materials)
    selected=(selected+[k for k in evidence if k.endswith('.methane') and k not in selected])[:3]
    selected += [k for k in evidence if k=='temperature.discussion']
    selected += [k for k in evidence if k.endswith('.heat_kwh') or k.endswith('.electricity_kwh')][:2]
    payload['evidence']={k:{f:evidence[k].get(f) for f in ['label','value','unit','level']} for k in selected}
    payload['input_alternatives']=[{'material':c.get('material'),'quantity':c.get('quantity'),'unit':c.get('unit')} for c in state.advanced['farmer_consultation'].get('components',[])]
    payload.update(tasks=state.advanced['farmer_consultation']['tasks'],recommended_question=priority_question(state,results),
        economics={'profit_established':eco.get('profit_established',False),'region_confirmed':eco.get('region_confirmed',False),
                   'fuel_energy_kwh':[r['analysis']['energy']['outputs'].get('potential_fuel_kwh') for r in eco.get('scenarios',[]) if r['analysis']['energy']['outputs']][:3]},
        temperature={'discussion_temperature_c':process.get('discussion_temperature_c'),'user_temperature_c':process.get('user_temperature_c'),'setpoint_validated':False,'heating_costs_known':False})
    # No full provenance trees or irrelevant concept catalog in the small context.
    return payload

EXPLANATION_SCHEMA={'type':'object','properties':{'conclusion':{'type':'string','maxLength':300},'explanation':{'type':'string','maxLength':240}},
                    'required':['conclusion','explanation'],'additionalProperties':False}

def explanation_context(results,state,query,evidence):
    payload=synthesis_context(results,state,query,evidence)
    selected=list(payload['evidence'])[:5]
    # Planning saw the original input and tools. At publication, only verified
    # qualitative findings are needed: do not make the small model copy tables.
    science=results.get('assess_substrate_potential',{});eco=results.get('evaluate_partial_economics',{});process=results.get('assess_process_evidence',{}).get('temperature_consultation',{})
    from src.advisor.catalog import name
    materials={c['material'] for s in science.get('scenarios',[]) for c in s.get('components',[])}
    if not materials and state.value('material') not in {None,'mixture'}:materials.add(state.value('material'))
    return {'Запрошенные задачи':[{'methane':'оценка метана','temperature':'температурный режим','economics':'экономический смысл','risks':'применимые риски и недостающие данные'}[t] for t in payload['tasks']],
        'Проверенные качественные выводы':[(c.get('text') or {}).get('ru') for c in results.get('search_scientific_sources',{}).get('claims',[]) if set(c.get('topics',[])) & {'ph','loading','co_digestion','low_gas'}][:4],
        'Сырьё':[name(m) for m in sorted(materials)],
        'Метан':{'Состояние оценки':('Python рассчитал условный литературный потенциал партии.' if any(s.get('methane_m3') for s in science.get('scenarios',[])) else 'Численный потенциал пока не рассчитан.'),
                  'Выработка установки':'Измерений нет: фактический выход неизвестен; нельзя утверждать, что газ уже произведён или не произведён.',
                  'Запрошен определённый срок':science.get('target_days') is not None,
                  'Выход за срок обоснован':any(s.get('time_yield',{}).get('methane_l') for s in science.get('scenarios',[])),
                  'Более высокий потенциал среди рассмотренных образцов':eco.get('potential_dominates_other_material_scenarios',[])},
        'Температура':{'Есть изученный мезофильный вариант для обсуждения':process.get('discussion_temperature_c') is not None,
                      'Оптимум и уставка проверены на установке':False,
                      'Расход на подогрев установлен':any(v['heat_balance'].get('heating_input_kwh') is not None for v in process.get('options',[]))},
        'Экономика':{'Полезная энергия оценена':any(r['analysis']['energy']['outputs'] for r in eco.get('scenarios',[])),
                    'Прибыль подтверждена':eco.get('profit_established',False),'Полные затраты неизвестны':not eco.get('profit_established',False)},
        'Публикация':'Все числовые результаты, условия источников и один уточняющий вопрос выводит Python отдельно. Объясни по-русски смысл оценки и неопределённость. Не переписывай числа, не добавляй новых научных утверждений.'},selected

def canonical_explanation(raw,selected,results,state):
    if set(raw)=={'conclusion','explanation'}:
        if any(not isinstance(raw[k],str) or re.search(r'[0-9]',raw[k]) for k in raw):
            from src.agent.providers import ProviderError
            raise ProviderError('Explanatory prose contract: numeric values belong to typed Python result blocks')
        if state.language=='ru' and not re.search(r'[А-Яа-яЁё]',' '.join(raw.values())):
            from src.agent.providers import ProviderError
            raise ProviderError('Explanatory prose contract: expected Russian language')
        return {**raw,'limitations':[],'next_question':priority_question(state,results),'evidence_ids':selected,
                'decision':'not_established' if 'evaluate_partial_economics' in results else 'not_applicable'}
    # Existing custom providers may still implement the original internal protocol.
    return raw

def compose(results,state,verification=None):
    """Present actual tool outputs; all arithmetic belongs to the shared engines."""
    from src.agent.autonomous import _sources
    science=results.get('assess_substrate_potential',{});eco=results.get('evaluate_partial_economics',{});proc=results.get('assess_process_evidence',{}).get('temperature_consultation',{})
    comparison=state.advanced.get('temperature_comparison_c',[])
    failed=verification is not None and verification.get('status')=='error'
    bad={c.get('scenario') for c in (verification or {}).get('checks',[]) if not c.get('passed')}
    safe=lambda row:not failed or bool(bad) and None not in bad and row.get('id') not in bad
    sections=[];known=[s for s in science.get('scenarios',[]) if s.get('methane_m3') and safe(s)]
    conclusion='Литературный ориентир метана рассчитан; это не измеренная выработка установки.' if known else 'Научные профили проверены; надёжный численный ориентир пока не получен.'
    if not science and proc:conclusion='Научные источники дают ориентиры температурного режима; настройка конкретной установки требует проверки её условий.'
    if eco:conclusion+=' Экономическую выгоду определяют полезное использование газа и полные расходы; прибыль пока не подтверждена.' if not eco.get('profit_established') else 'Экономика рассчитана по введённым условиям.'
    sections.append({'title':'Краткий вывод','body':conclusion})
    if comparison:
        rows=[]
        for scenario in known:
            if scenario.get('methane_m3') is None:continue
            for c in scenario['components']:
                t=c.get('source_conditions',{}).get('temperature_c')
                if t in comparison:
                    line=f"{t:g} °C: {span(scale(scenario['methane_m3'],1000))} л CH₄ — литературный потенциал всей партии."
                    if scenario.get('conditional_reference_energy'):line+=f" Условная энергия: {span(scenario['conditional_reference_energy']['value'])} кВт·ч."
                    rows.append(line)
        rows.append('Энергия — отдельный условный расчёт по справочнику FNR (9.97 кВт·ч/м³ сухого CH₄): предполагается совместимая объёмная база, которой исходный опыт полностью не подтверждает. Это не полезное тепло и не измерение. Источник: https://biogas.fnr.de/daten-und-fakten/faustzahlen')
        rows.append('Это литературные условия, не измеренная выработка установки и не прогноз за фиксированное число дней.')
        rows.append('При прочих равных более тёплый вариант требует больше тепла. Сравнивать нужно полезную энергию газа за вычетом начального нагрева, теплопотерь и перемешивания. Без тепловых исходных данных численный чистый баланс неизвестен.')
        rows.append('Условный выбор: мезофильный вариант имеет смысл при доступном недорогом тепле, адаптированном инокуляте и устойчивом процессе. При ограниченном подогреве более прохладный режим можно рассматривать как отдельный сценарий, но его длительность и фактическую производительность нужно подтвердить. Автоматически повышать температуру не следует.')
        sections.append({'title':'Сравнение температур','body':'\n'.join(dict.fromkeys(rows))})
    if failed:sections.append({'title':'Ограничение расчёта','body':'Часть расчётных данных не прошла проверку; её численные результаты не показываю. Другие доступные части анализа сохранены.'})
    if science and not comparison:
        gas=[]
        for s in known:
            temps=sorted({c['source_conditions']['temperature_c'] for c in s['components'] if c.get('source_conditions',{}).get('temperature_c') is not None})
            if not temps:
                from src.advisor.catalog import profiles
                temperatures={p['id']:p['conditions'].get('temperature_c') for p in profiles()}
                temps=sorted({temperatures[p] for p in s['profile_ids'] if temperatures.get(p) is not None})
            label='при '+', '.join(f'{v:g}' for v in temps)+' °C в источнике' if temps else 'при условиях источника'
            gas.append(f"{s['label']}, {label}: {span(scale(s['methane_m3'],1000))} л CH₄ для всей партии.")
            for c in s['components']:
                used=c['properties_used']
                cond=c.get('source_conditions',{})
                if cond.get('feed_volume_fraction_high') and state.value('reactor_total_volume_l') and c.get('volume_l') and c['volume_l']['low']/state.value('reactor_total_volume_l')>cond['feed_volume_fraction_high']:
                    gas.append('Вся партия относительно номинальной ёмкости уже превышает умеренную объёмную загрузку этого опыта. Литературный потенциал относится ко всему сырью, не к одной такой загрузке; рабочий объём и разделение на партии требуют проверки.')
                if used.get('vs_kg_l'):gas.append(f"Органическое сухое вещество источника {span(scale(used['vs_kg_l']['range'],1000))} г/л; по указанному объёму рассчитано {span(c['vs_mass_kg'])} кг. Плотность и масса влажного навоза не подставлялись: используется концентрация на литр.")
                elif c.get('vs_mass_kg'):gas.append(f"Расчётная масса органического сухого вещества {span(c['vs_mass_kg'])} кг; влажная масса {span(c['wet_mass_kg'])} кг.")
                bmp=used.get('bmp_ml_g_vs',{}).get('range')
                if bmp:gas.append(f"BMP источника: {span(bmp)} мл CH₄/г органического сухого вещества.")
            time=s.get('time_yield',{})
            if time.get('days') is not None:gas.append(f"Выход за {time['days']:g} дней: "+(span(time['methane_l'])+' л CH₄ по явно заданной кинетической модели.' if time['methane_l'] else 'не установлен: применимая кинетика отсутствует. Потенциал не подменяет выход за срок.'))
        if not known:gas.append('Совместимой цепочки пока нет. Можно уточнить вид и состояние сырья; самостоятельно подбирать научные коэффициенты фермеру не требуется.')
        if state.value('duration_days') is None:gas.append('Срок выработки не задан; число дней не назначаю.')
        gas.append('Это отдельные литературные варианты, не доверительный интервал и не гарантия. Состав и подготовка партии должны быть сопоставимы с исследованием. Метан не равен всему биогазу.')
        sections.append({'title':'Оценка метана','body':'\n'.join(dict.fromkeys(gas))})
    if proc:
        parts=[];discussion=proc['discussion_temperature_c']
        if discussion is not None:parts.append(f'Отправной точкой для обсуждения может быть мезофильный режим около {discussion:g} °C: он представлен в исследованиях этого сырья. Это не проверенная уставка оборудования; нужны адаптированный инокулят и стабильный контроль.')
        else:parts.append('Подходящая численная температура для этого сырья не подтверждена. Объём реактора не определяет её сам по себе.')
        if proc['user_temperature_c'] is not None:parts.insert(0,f"Условие пользователя: {proc['user_temperature_c']:g} °C. Это не измерение и не уставка; литературная температура ниже указана отдельно.")
        parts.append('Мезофильный вариант требует меньше подогрева, чем более горячий термофильный при прочих равных. Повышение температуры может менять аммиачный риск и устойчивость; оно не гарантирует улучшение процесса.')
        for option in proc['options']:
            h=option['heat_balance'];p=f"Подогрев для варианта {option['temperature_c']:g} °C: "
            if h.get('heating_input_kwh') is None:continue
            p+=f"{h['heating_input_kwh']:.5g} кВт·ч." if h.get('heating_input_kwh') is not None else 'полный расход не определён.'
            for key,label in [('initial_heating_kwh','Начальный нагрев'),('maintenance_heating_kwh','Поддержание'),('auxiliary_kwh','Перемешивание и прочие нагрузки')]:
                if h.get(key) is not None:p+=f" {label}: {h[key]:.5g} кВт·ч."
            parts.append(p)
        if all(o['heat_balance'].get('heating_input_kwh') is None for o in proc['options']):parts.append('Затраты на подогрев пока неизвестны. Нужны масса загрузки с водой и инокулятом, начальная и наружная температура, утепление, длительность и расход мешалки. Начальный нагрев и теплопотери учитываются отдельно; номинальный объём не заменяет массу. Команды нагревателю не отправляются.')
        sections.append({'title':'Температура и энергия','body':'\n'.join(parts)})
    if eco:
        parts=[]
        if eco.get('potential_dominates_other_material_scenarios'):
            parts.append('По рассмотренным литературным образцам больший условный потенциал метана у '+', '.join(eco['potential_dominates_other_material_scenarios'])+'. Это сравнение газового ориентира; лидер по чистой прибыли без полных затрат не установлен.')
        for row in eco.get('scenarios',[]):
            if not safe(row):continue
            a=row['analysis'];out=a['energy']['outputs']
            if not out:continue
            scenario=next((s for s in science.get('scenarios',[]) if s['id']==row['id']),{})
            temps=sorted({c['source_conditions']['temperature_c'] for c in scenario.get('components',[]) if c.get('source_conditions',{}).get('temperature_c') is not None})
            label=scenario.get('label','Отдельный литературный вариант')+(' (опыт при '+', '.join(f'{v:g}' for v in temps)+' °C)' if temps else '')
            parts.append(f"{label}: энергия метана {span(out['potential_fuel_kwh'])} кВт·ч; полезное тепло {span(out['heat_only_kwh'])} кВт·ч ИЛИ электричество {span(out['electricity_only_kwh'])} кВт·ч. Эти альтернативы не складываются.")
            parts.append('Сбор газа и КПД приняты как условные сценарии оборудования, не измерены. Теплота сгорания и база объёма газа должны быть совместимы.')
            parameters=a['energy']['parameters']
            if all(parameters.get(k) for k in ['recovery_fraction','thermal_efficiency','electrical_efficiency']):
                parts.append('Принятые допущения: сбор газа '+span(scale(parameters['recovery_fraction'],100))+'%, КПД получения тепла '+span(scale(parameters['thermal_efficiency'],100))+'%, электричества '+span(scale(parameters['electrical_efficiency'],100))+'%. Это примеры оборудования, не универсальные свойства навоза.')
            price=a['prices']['electricity'];obs=price.get('observation',{})
            if price.get('value') is not None:
                parts.append(f"Электроэнергия: {price['value']:g} KZT/кВт·ч, регион {eco['region']}; "+('регион подтверждён.' if eco.get('region_confirmed') else 'регион условный.')+f" Источник: {price.get('source')}; дата {price.get('published_at') or obs.get('published_at') or obs.get('effective_from') or 'не указана'}.")
                if obs.get('is_stale') or 'stale_reference' in price.get('reasons',[]):parts.append('Цена устарела; обозначать её текущим тарифом нельзя.')
                parts.append('Категория потребителя, тип тарифа и налоги должны соответствовать вашему договору; справочный ряд не подтверждает тариф фермы.')
            else:parts.append('Применимый тариф в рыночном хранилище не найден. Цену не подставляю: экономия = полезная энергия × ваш применимый тариф.')
            for alternative in a['scenarios']:
                if alternative['id'] in {'B_heat','C_electricity'} and alternative.get('gross_benefit_reference_kzt'):
                    parts.append(('Использование тепла' if alternative['id']=='B_heat' else 'Выработка электричества')+': валовая ценность '+span(alternative['gross_benefit_reference_kzt'])+' KZT до затрат, не прибыль.')
                if alternative.get('net_result_kzt') is not None:parts.append('Чистый результат соответствующего сценария: '+span(alternative['net_result_kzt'])+' KZT по введённым условиям.')
        if not parts:parts.append('Рыночные записи проверены; без применимого газового ориентира денежный результат пока не установлен.')
        parts.append('В небольшой установке теплопотери и работа мешалки могут поглотить полезный выход. Переработка может иметь смысл при спросе на тепло и достаточно малых полных расходах. Прибыль и окупаемость без этих расходов не подтверждены; неизвестные затраты не равны нулю.')
        parts.append('Чувствительность: при неизменных условиях валовая ценность пропорциональна полезной энергии и применимому тарифу. Для безубыточности все расходы должны быть ниже полезной валовой ценности. Тариф природного газа не служит ценой продажи сырого биогаза.')
        sections.append({'title':'Экономическая оценка','body':'\n'.join(dict.fromkeys(parts))})
    search=results.get('search_scientific_sources',{})
    claims=[c for c in search.get('claims',[]) if set(c.get('topics',[])) & {'ph','loading','co_digestion','low_gas'}]
    if claims:
        sections.append({'title':'Риски и научные ограничения','body':'\n'.join(dict.fromkeys(c['text']['ru'] for c in claims))})
    sections.append({'title':'Практические ограничения','body':'Номинальная вместимость не равна рабочему объёму. До загрузки проверьте объём сырья вместе с водой, инокулятом и остатком, газовое пространство и конструкцию установки. Оценка всей партии не является выходом одного цикла; литературные параметры не становятся вашими измерениями.'})
    from src.optimizer.capacity import assess_dialogue_state,render_capacity_notice
    loading=assess_dialogue_state(state)
    if loading.get('simultaneous_load_possible') is False:sections.insert(0,{'title':'Ограничение загрузки','body':render_capacity_notice(loading,'ru')})
    return sections,priority_question(state,results),_sources(results)
