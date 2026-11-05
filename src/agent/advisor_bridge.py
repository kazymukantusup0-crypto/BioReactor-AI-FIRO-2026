"""Inventory state and advisory routing; no model-proposed mixture quantities."""
import copy,json,re,time
from src.agent.dialogue_types import Entity,Question
from src.agent.dialogue_memory import fact
from src.agent.mixture_parser import parse_turn
from src.advisor.schemas import AdvisorRequest,Component,ComparisonRequest
from src.advisor import catalog
from src.market.domain import utcnow

def prepare(text,state,extraction):
    plan=parse_turn(text,state)
    if plan and len(plan['components'])>1 and re.search(r'\bили\b|\bor\b|\bversus\b',text,re.I) and re.search(r'выгод|сравн|compar|better',text,re.I):
        plan['scenario']=True  # Compared alternatives do not assert combined ownership.
    active=bool(plan or state.mixture_components or state.mixture_scenario_components)
    if not active:return extraction,None
    multi=len(plan['components'])>1 if plan else state.advisor_inventory_mode=='mixture'
    if multi or state.advisor_inventory_mode=='mixture':
        extraction.entities=[e for e in extraction.entities if e.name not in {'material','quantity','unit','mass_kg','material_volume_l','vs_mass_kg','density_kg_l','ts_percent','vs_percent','vs_basis'}]
        extraction.entities.append(Entity(name='material',value='mixture',evidence=text))
    elif plan and len(plan['components'])==1 and not plan['scenario']:
        c=plan['components'][0]
        extraction.entities=[e for e in extraction.entities if e.name not in {'material','quantity','unit','mass_kg','material_volume_l'}]
        extraction.entities.extend([Entity(name='material',value=c.material,evidence=c.evidence or text),Entity(name='quantity',value=c.quantity,unit=c.unit,evidence=c.evidence or text),Entity(name='unit',value=c.unit,evidence=c.evidence or text)])
    if plan and plan['scenario']:
        extraction.entities=[e for e in extraction.entities if e.name not in {'quantity','unit','mass_kg','material_volume_l','vs_mass_kg','density_kg_l','ts_percent','vs_percent','vs_basis','bmp_ml_ch4_g_vs'}]
    # Hyphenated reactor capacity must remain separate from a substrate quantity.
    match=re.search(r'(\d+(?:[.,]\d+)?)\s*[-–]?\s*литров\w*\s+реактор',text,re.I)
    if match:extraction.entities.append(Entity(name='reactor_total_volume_l',value=float(match[1].replace(',','.')),unit='L',evidence=match.group()))
    return extraction,plan

def commit(state,prior,plan,text,extraction=None):
    if plan:
        state.analytical_mode='alternatives' if len(plan['components'])>1 and re.search(r'\bили\b|\bor\b|\bversus\b',text,re.I) and re.search(r'выгод|сравн|compar|better',text,re.I) else 'mixture'
        state.active_mixture_scenario=bool(plan['scenario'])
        components=[c.model_dump(mode='json') for c in plan['components']]
        if plan['scenario']:
            state.mixture_scenario_components=components
            if not state.mixture_components and plan.get('baseline_components'):state.mixture_components=[c.model_dump(mode='json') for c in plan['baseline_components']]
        else:state.mixture_components=components;state.mixture_scenario_components=[];state.mixture_revision+=1
        if len(components)>1 or prior.advisor_inventory_mode=='mixture':state.advisor_inventory_mode='mixture'
        else:state.advisor_inventory_mode='single'
        state.mixture_history=(prior.mixture_history+[{'at':utcnow().isoformat(),'action':plan['action'],'is_hypothetical':plan['scenario'],'components':components}])[-30:]
    if state.advisor_inventory_mode=='mixture':
        for key in ['quantity','unit','mass_kg','material_volume_l','vs_mass_kg','density_kg_l','ts_percent','vs_percent','vs_basis']:state.facts.pop(key,None)
        state.derived={}
    if text.lstrip().startswith('{'):
        raw=json.loads(text)
        if 'advisor_inputs' in raw:
            if not isinstance(raw['advisor_inputs'],dict):raise ValueError('advisor_inputs requires an object')
            state.advisor_settings={**prior.advisor_settings,**raw['advisor_inputs']}
    if len(state.mixture_components)==1 and not (plan and plan['scenario']) and extraction:
        c=state.mixture_components[0];props=dict(c.get('properties',{}));explicit={e.name:e.value for e in extraction.entities if e.provenance=='USER_CONFIRMED'}
        if not plan and 'quantity' in explicit:
            c.update(quantity=state.value('quantity'),unit=state.value('unit'))
        if 'material_state' in explicit:
            previous=next((p for p in prior.mixture_components if p['id']==c['id']),{})
            if previous.get('material_state',c.get('material_state'))!=explicit['material_state']:
                props={};c['reference_profile_id']=None
            c['material_state']=explicit['material_state']
        for axis in ['physical_state','decay_state']:
            if axis in explicit:c[axis]=explicit[axis]
        for source,target,factor in [('density_kg_l','density_kg_l',1),('ts_percent','ts_fraction',.01),('bmp_ml_ch4_g_vs','bmp_ml_g_vs',1)]:
            if source in explicit:props[target]=explicit[source]*factor
        if 'vs_percent' in explicit and state.value('vs_basis') in {'TS','fresh_mass'}:props['vs_fraction_of_ts' if state.value('vs_basis')=='TS' else 'vs_fraction_wet']=explicit['vs_percent']*.01
        c['properties']=props
    # Validate typed settings before this state is accepted by the agent.
    if state.mixture_components or state.mixture_scenario_components:request_data(state,plan and plan['scenario'])
    return state

def applicable(state,text):
    if not (state.mixture_components or state.mixture_scenario_components):return False
    if set(state.intents)&{'model_info','reactor_status','price_history'}:return False
    return True

def request_data(state,scenario=False):
    from src.agent.research_bridge import request_data as existing
    old=existing(state);settings=copy.deepcopy(state.advisor_settings)
    components=state.mixture_scenario_components if scenario or not state.mixture_components else state.mixture_components
    data={'components':components,'assume_common_dry_gas_basis':True,'reactor_total_volume_l':state.value('reactor_total_volume_l'),
          'decision':old['decision'],'region':old['region'],'region_confirmed':old['region_confirmed'],'online':old['online'],**settings}
    return AdvisorRequest.model_validate(data)

def _span(value,unit='',digits=2):
    if value is None:return None
    return (f"{value['low']:.{digits}f}" if abs(value['high']-value['low'])<1e-10 else f"{value['low']:.{digits}f}–{value['high']:.{digits}f}")+(' '+unit if unit else '')

def response_text(state,result,plan,message=''):
    language=state.language
    def t(ru,en,kk):return {'ru':ru,'en':en,'kk':kk}[language]
    mix=result['mixture'];mass=_span(mix['total_wet_mass_kg'],'кг' if language!='en' else 'kg');count=len(mix['components']);value=_span(mix['additive_methane_reference_m3'],'м³' if language!='en' else 'm³');partial=_span(mix['known_component_additive_subtotal_m3'],'м³' if language!='en' else 'm³')
    changed=bool(plan and plan.get('changed') and state.mixture_revision>1)
    p=[t(('Состав обновлён. ' if changed else '')+f'Компонентов: {count}.'+(f' Общая влажная масса: {mass}.' if mass else ' Общая масса пока неизвестна: для части объёмов нужна плотность.'),
         ('Composition updated. ' if changed else '')+f'Components: {count}.'+(f' Total wet mass: {mass}.' if mass else ' Total mass needs density for the volume-based components.'),
         ('Құрам жаңартылды. ' if changed else '')+f'Компонент саны: {count}.'+(f' Жалпы ылғал масса: {mass}.' if mass else ' Көлемі белгілі бөліктердің тығыздығы қажет.'))]
    if plan and plan['scenario']:p[0]=t('Это отдельный пример «что если»; исходный состав не изменён. ','This is a separate what-if example; confirmed inventory is unchanged. ','Бұл бөлек шартты мысал; расталған құрам өзгерген жоқ. ')+p[0]
    if value:p.append(t(f'Сумма отдельных ориентиров даёт {value} метана. Это условный аддитивный расчёт, а не измеренный выход смешанного сырья.',f'The component references add to {value} methane. This additive scenario is not a measured co-digestion yield.',f'Жеке бөліктердің бағалауы бойынша метан {value}. Бұл — аддитивті сценарий, қоспаның өлшенген шығымы емес.'))
    elif partial:p.append(t(f'Для известных частей получается ориентир {partial} метана; полный выход смеси пока не рассчитан. Неизвестные части не считаются нулём.',f'Known parts give an additive reference of {partial} methane; the full mixture is not estimated. Missing parts are not zero.',f'Белгілі бөліктер үшін метан бағасы {partial}; толық қоспаның шығымы есептелмеді. Белгісіз бөліктер нөл деп алынбайды.'))
    else:p.append(t('Для полного выхода пока не хватает сопоставимых характеристик сырья. Числа другого материала не подставлены.','Comparable substrate properties are missing; values from another material were not substituted.','Сәйкес шикізат қасиеттері жеткіліксіз; басқа материалдың мәндері қойылмады.'))
    if len(mix['components'])==1 and mix['components'][0]['material']=='manure':p.append(t('Вид навоза ещё не указан. Профиль навозной жижи КРС можно использовать только как отдельный условный пример, а не как подтверждённое свойство этого сырья.','Manure species is unknown. A cattle-slurry profile would be a separate conditional example, not an identified material.','Көңнің жануар түрі белгісіз. Сиырдың сұйық көңі профилі тек бөлек шартты мысал бола алады.'))
    if result.get('conditional_reference_case'):
        ref=result['conditional_reference_case'];p.append(t(f"Если это навозная жижа КРС, отдельный литературный пример даёт {_span(ref['mixture']['additive_methane_reference_m3'],'м³')} метана. Вид сырья этим не подтверждается.",f"If it is cattle slurry, a separate literature example gives {_span(ref['mixture']['additive_methane_reference_m3'],'m³')} methane. This does not confirm the species.",f"Егер бұл сиырдың сұйық көңі болса, бөлек әдеби мысал метанды {_span(ref['mixture']['additive_methane_reference_m3'],'м³')} деп бағалайды. Бұл жануар түрін растамайды."))
    effective=result.get('conditional_reference_case') or result
    bg=effective['decision_analysis']['biogas'];gas=bg.get('potential_biogas_m3');fraction=bg.get('methane_fraction')
    if gas and fraction:
        percent=_span({'low':fraction['low']*100,'high':fraction['high']*100},'%',0)
        gas_text=t(f" Отдельный условный ориентир общего биогаза: {_span(gas,'м³')} при {percent} метана и допущении сопоставимых условий газа. Метан уже входит в этот объём; это не обещание реального сбора.",f" A separate conditional total-biogas reference is {_span(gas,'m³')} at {percent} methane, assuming comparable gas references. Methane is already included; this is not guaranteed collected gas.",f" Газ шарттары сәйкес деген болжамда, {percent} метан үлесімен жалпы биогаз бағасы {_span(gas,'м³')}. Метан осы көлемге кіреді; бұл нақты жиналатын газға кепілдік емес.")
        p[-1 if result.get('conditional_reference_case') else 1]+=gas_text
    studies=effective['temperature']['studies'];temps=sorted({v for s in studies for v in s['temperatures_c']});show_conditions=not changed or bool(re.search(r'температур|градус|temperature|врем|срок|сут|duration|how long|уақыт',message,re.I))
    if result['temperature']['candidate']:
        temp=result['temperature']['candidate']['temperature_c'];p.append(t(f'Для заявленных условий можно рассмотреть {temp:g} °C как консультационный вариант; универсальный оптимум не доказан.',f'For the declared conditions, {temp:g} °C is an advisory candidate, not a proven universal optimum.',f'Берілген шарттарға {temp:g} °C кеңестік нұсқа ретінде қаралады, әмбебап оңтайлы мән дәлелденбеген.'))
    elif temps and show_conditions:p.append(t('В сопоставимых и смежных работах изучались '+', '.join(str(x) for x in temps)+' °C. Пока рекомендую сравнивать эти режимы с учётом инокулята, контроля и нагрева; назначать температуру только по литрам нельзя.',
                        'Related studies tested '+', '.join(str(x) for x in temps)+' °C. Compare these with inoculum, control and heat demand; litres alone cannot select a temperature.',
                        'Ұқсас зерттеулерде '+', '.join(str(x) for x in temps)+' °C қаралды. Инокулят, бақылау және жылыту ескерілуі тиіс; литр саны температураны анықтамайды.'))
    elif not temps and show_conditions:p.append(t('Подходящий температурный режим для этого состава пока не подтверждён.','A suitable temperature for this composition is not established.','Бұл құрамға сәйкес температура әлі расталмады.'))
    kinds=effective['duration']['studies'];bmp=[str(v) for s in kinds if s['kind']=='BMP_INCUBATION' for v in s['days']];hrt=[str(v) for s in kinds if s['kind']=='HRT' for v in s['days']]
    if (bmp or hrt) and show_conditions:p.append(t(('Лабораторное испытание в источниках: '+', '.join(dict.fromkeys(bmp))+' суток. ' if bmp else '')+('Непрерывное удерживание в отдельных работах: '+', '.join(dict.fromkeys(hrt))+' суток. ' if hrt else '')+'Это разные сроки; длительность вашей партии и запуск ещё не определены.',
        ('Source laboratory assays: '+', '.join(dict.fromkeys(bmp))+' days. ' if bmp else '')+('Continuous retention examples: '+', '.join(dict.fromkeys(hrt))+' days. ' if hrt else '')+'These are different durations; your batch completion and start-up are not predicted.',
        ('Зертханалық сынақ: '+', '.join(dict.fromkeys(bmp))+' тәулік. ' if bmp else '')+('Үздіксіз ұстау мысалдары: '+', '.join(dict.fromkeys(hrt))+' тәулік. ' if hrt else '')+'Бұлар әртүрлі; сіздің партия мен іске қосу мерзімі әлі анықталмады.'))
    if count>1 and not changed:p.append(t('Пока не объявляю смесь оптимальной: совместная переработка может ускорить разложение или вызвать закисление и ингибирование. Это требует измерений, а не коэффициента «синергии».','No blend is declared optimal: co-digestion can help or inhibit the process. Measurements are needed instead of an invented synergy factor.','Қоспа оңтайлы деп жарияланбайды: бірлесіп ашыту үдерісті жақсартуы да, тежеуі де мүмкін. Жорамал коэффициент емес, өлшемдер қажет.'))
    if re.search(r'загруз|вмест|реактор|reactor|charge|сый|реактор',message,re.I):
        g=result['decision_analysis']['feasibility']
        p.append(t('Загрузить всё сразу пока нельзя обоснованно рекомендовать: '+('расчёт уже показывает превышение объёма.' if g['status']=='PHYSICALLY_INFEASIBLE' else 'нужны фактический объём смеси, подтверждённый рабочий объём, место для газа, инокулюм и режим подачи. Полные 200 л не означают 200 л сырья.' if request_total_200(result) else 'нужны фактический объём смеси, рабочий объём, место для газа, инокулюм и режим подачи.'),
                   'A single full charge cannot yet be recommended. Confirm actual mixture volume, working capacity, headspace, inoculum and feed mode. Total vessel size is not feed capacity.',
                   'Барлығын бірден жүктеу әзірше ұсынылмайды. Қоспаның нақты көлемі, жұмыс көлемі, газға бос орын, инокулят және беру режимі қажет. Толық көлем шикізат сыйымдылығы емес.'))
        if re.search(r'можно\s+загруз|вс[её]\s+сразу|can.*load|all.*once',message,re.I):p.insert(0,p.pop())
    return p

def request_total_200(result):return result.get('request',{}).get('reactor_total_volume_l')==200

def respond(agent,text,extraction,proposal,started,plan=None):
    from src.advisor.service import analyze
    from src.advisor.optimization import compare,suggestions
    from src.market.service import get_store
    from src.agent.human_response import sections
    state=agent.state;request=request_data(state,bool(plan and plan['scenario']));store=agent.registry.market_store or get_store()
    result=agent.registry.execute('analyze_substrate_mixture',{'advisor_request':request.model_dump(mode='json')},{},text);comparison=None
    if result.get('status')=='error':
        return {'conversation_version':'7','analysis_version':'7.6','mode':'tool_error','answer':result['message'],'tools':[{'tool':'analyze_substrate_mixture','status':'error','result':result}],'missing':[],'context':dict(agent.context),'context_updated':True,'provider_status':list(agent.llm.status),'actuator_access':False}
    if len(request.components)>1 and re.search(r'выгод|лучш\w*\s+сме|оптим|which\s+mixture|best\s+mix|қай\s+қоспа',text,re.I):comparison=agent.registry.execute('compare_substrate_mixtures',{'comparison_request':ComparisonRequest(base=request,candidates=suggestions(request)).model_dump(mode='json')},{},text)
    paragraphs=response_text(state,result,plan,text);pending=None
    if comparison:
        def localized(ru,en,kk):return {'ru':ru,'en':en,'kk':kk}[state.language]
        paragraphs.insert(0,localized(f"Сравнил {len(comparison.get('candidates',[]))} варианта в пределах имеющегося сырья. Самый выгодный пока не установлен: нужны применимые цены, все расходы и проверка стабильности смеси.",f"Compared {len(comparison.get('candidates',[]))} variants within available inventory. A most profitable blend is not established: eligible prices, full costs and stability evidence are needed.",f"Қолдағы шикізат шегінде {len(comparison.get('candidates',[]))} нұсқа салыстырылды. Ең тиімді қоспаны анықтау үшін сәйкес баға, барлық шығын және тұрақтылық деректері қажет."))
    generic=next((c for c in request.components if c.material=='manure'),None)
    unknown=next((c for c in request.components if c.material=='cattle_manure' and c.material_state=='unknown'),None)
    def t(ru,en,kk):return {'ru':ru,'en':en,'kk':kk}[state.language]
    if generic:
        state.advisor_pending_component=generic.id
        pending=Question(id='advisor-species',text=t('Это навоз КРС, свиной или другого животного?','Is it cattle, pig or another manure?','Бұл сиыр, шошқа әлде басқа жануардың көңі ме?'),options=[],fields=['advisor_material'],reason='Species is not inferred from slurry alone')
    elif unknown:
        state.advisor_pending_component=unknown.id
        pending=Question(id='advisor-state',text=t('Коровий навоз в этом составе — жидкая жижа или навоз с подстилкой?','Is the cattle manure slurry or bedded solid manure?','Құрамдағы сиыр көңі сұйық па, әлде төсенішпен араласқан ба?'),options={'ru':['Навозная жижа','С подстилкой'],'en':['Cattle slurry','Bedded manure'],'kk':['Сұйық көң','Төсенішті көң']}[state.language],fields=['advisor_material_state'])
    elif request.decision.reactor.reactor_working_volume_l is None and 'reactor_working_volume_l' not in state.decision_unavailable:
        pending=Question(id='advisor-working-volume',text=t('Какой рабочий объём реактора подтверждён, отдельно от полного объёма?','What working liquid volume is confirmed, separately from total capacity?','Толық көлемнен бөлек, расталған жұмыс көлемі қандай?'),options=[],fields=['reactor_working_volume_l'])
    state.pending_question=pending;agent.history=(agent.history+[text])[-8:];agent.last_pending=[]
    trace=[{'tool':'analyze_substrate_mixture','status':result['status'],'input_origin':'validated_component_inventory_and_separate_scenarios','result':{'status':result['status'],'message':paragraphs[0],'advisor_result':result}}]
    if comparison:trace.append({'tool':'compare_substrate_mixtures','status':comparison['status'],'input_origin':'availability_constrained_candidate_scenarios','result':{'status':comparison['status'],'message':comparison.get('reason',comparison.get('message')),'comparison':comparison}})
    sources=[{'title':s['title'],'url':s['url']} for s in result['sources'] if s.get('url')]
    return {'conversation_version':'7','analysis_version':'7.6','human_response_version':'7.6','mode':'llm_tools' if proposal else 'deterministic_tools_no_llm','answer':'\n\n'.join(paragraphs),
        'user_facing_answer':{'paragraphs':paragraphs,'sections':sections(paragraphs,state.language),'question':pending.model_dump() if pending else None,'sources':sources,'modes':['substrate_advisor'],'assumptions':[]},
        'tools':trace,'provider_status':list(agent.llm.status),'missing':[],'context':dict(agent.context),'context_updated':True,'memory':state.model_dump(mode='json'),'pending_question':pending.model_dump() if pending else None,'actuator_access':False,
        'technical_metadata':{'advisor_result':result,'mixture_comparison':comparison,'component_inventory':state.mixture_components,'scenario_inventory':state.mixture_scenario_components,'mixture_revision':state.mixture_revision,
                              'extracted_entities':extraction.model_dump(),'confirmed_parameters':{k:v.model_dump() for k,v in state.facts.items() if v.provenance=='USER_CONFIRMED'},'latency_seconds':time.perf_counter()-started,'llm_proposal':proposal.model_dump() if proposal else None}}
