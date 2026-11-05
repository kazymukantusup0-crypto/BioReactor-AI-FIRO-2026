"""Task-specific execution and bounded, grounded presentation for v7.7."""
import hashlib,json,re,time,copy
from src.advisor.schemas import AdvisorRequest,Component,ComparisonRequest
from src.advisor import catalog
from src.agent.dialogue_types import Question
from src.market.domain import utcnow
from src.data.prepare import ROOT

def evidence_revision():
    return [(p.name,p.stat().st_mtime_ns,p.stat().st_size) for p in [ROOT/'data/research/reviewed_evidence.json',ROOT/'data/research/substrate_advisor.json',ROOT/'data/research/decision_references.json']]

def make_request(state):
    from src.agent.advisor_bridge import request_data
    from src.agent.research_bridge import request_data as legacy
    if state.mixture_components or state.mixture_scenario_components:return request_data(state,state.active_mixture_scenario)
    old=legacy(state);material=catalog.normalized(state.value('material') or '')
    quantity=state.value('quantity');unit=state.value('unit')
    if quantity is None:
        quantity=state.value('mass_kg') or state.value('material_volume_l');unit='kg' if state.value('mass_kg') is not None else 'L'
    props={}
    for k in ['density_kg_l','ts_fraction','vs_fraction_wet','vs_fraction_of_ts','bmp_ml_g_vs']:
        oldkey='bmp_ml_g_vs' if k=='bmp_ml_g_vs' else k
        if old.get(oldkey) is not None:props[k]=old[oldkey]
    component=Component(id='c1',material=material,material_state=old['material_state'],quantity=quantity or 1,unit=unit or 'kg',properties=props,
                        provenance='USER_CONFIRMED' if quantity else 'ASSUMED_FOR_SCENARIO',evidence='Confirmed single-material inventory' if quantity else 'Conditions-only reference; quantity has not been provided')
    return AdvisorRequest(components=[component],assume_common_dry_gas_basis=False,reactor_total_volume_l=old.get('reactor_total_volume_l'),decision=old['decision'],region=old['region'],region_confirmed=old['region_confirmed'],online=False)

def applicable(state,plan,text):
    if plan['delegate_legacy']:return False
    if 'reactor' in plan['goals']:return True
    if state.mixture_components or state.mixture_scenario_components:return True
    try:catalog.normalized(state.value('material') or '');return True
    except ValueError:return bool(re.search(r'^\s*(?:привет|здравствуй|hello|hi\b|сәлем)|что такое.*биогаз|what is biogas',text,re.I))

def span(value,unit='',digits=2):
    if not value:return None
    return (f"{value['low']:.{digits}f}" if abs(value['high']-value['low'])<1e-9 else f"{value['low']:.{digits}f}–{value['high']:.{digits}f}")+(' '+unit if unit else '')

def respond(agent,text,extraction,proposal,started,plan,edit_plan):
    state=agent.state;language=state.language
    def t(ru,en,kk):return {'ru':ru,'en':en,'kk':kk}[language]
    goals=plan['goals'];trace=[];pending=None;outputs={};cache_hits=0
    request=None
    try:request=make_request(state)
    except ValueError:pass
    if plan.get('definition'):request=None
    has_amount=bool(state.mixture_components or state.mixture_scenario_components or state.value('quantity') or state.value('mass_kg') or state.value('material_volume_l'))
    signature=hashlib.sha256(json.dumps({'request':request.model_dump(mode='json') if request else {},'evidence':evidence_revision()},sort_keys=True).encode()).hexdigest()
    reuse=(plan['detail'] or plan['one_sentence'] or plan.get('source_only')) and state.smart_cache.get('last',{}).get('signature')==signature and state.smart_cache.get('last',{}).get('goals')==goals
    def execute(name,context,key=None):
        nonlocal cache_hits
        fingerprint=copy.deepcopy(context)
        if key=='conditions' and not fingerprint['advisor_request'].get('feeding_period_days'):
            for c in fingerprint['advisor_request']['components']:c['quantity']=None;c['evidence']='Quantity does not determine reference biological conditions'
        digest=hashlib.sha256(json.dumps({'input':fingerprint,'evidence':evidence_revision()},sort_keys=True).encode()).hexdigest()
        cached=state.smart_cache.get(key or '',{})
        hit=bool(key and cached.get('signature')==digest)
        result=copy.deepcopy(cached['result']) if hit else agent.registry.execute(name,context,{},text)
        if hit and key=='conditions':
            from src.advisor.focused import geometry_for
            result['request']=copy.deepcopy(context['advisor_request']);result['geometry']=geometry_for(AdvisorRequest.model_validate(context['advisor_request']))
        json.dumps(result,allow_nan=False)
        trace.append({'tool':name,'status':result['status'],'cache_hit':hit,'input_origin':'validated_user_facts_and_scoped_evidence','result':result})
        if hit:cache_hits+=1
        if key and result.get('status')!='error':state.smart_cache[key]={'signature':digest,'result':copy.deepcopy(result)}
        return result
    if reuse:outputs=copy.deepcopy(state.smart_cache['last']['outputs']);cache_hits+=1
    elif plan.get('source_only'):outputs['catalog']=execute('get_substrate_catalog',{})
    elif 'reactor' in goals:outputs['reactor']=execute('get_reactor_status',{})
    elif request and goals:
        economical='economics' in goals or 'compare' in goals or text.lstrip().startswith('{') and bool(state.decision_settings)
        if economical:
            if state.mixture_components or state.mixture_scenario_components:
                outputs['full']=execute('analyze_substrate_mixture',{'advisor_request':request.model_dump(mode='json')})
            else:
                from src.agent.research_bridge import request_data
                outputs['legacy']=execute('research_and_estimate',{'research_request':{**request_data(state),'online':False}})
            if 'compare' in goals and len(request.components)>1:
                from src.advisor.optimization import suggestions
                outputs['comparison']=execute('compare_substrate_mixtures',{'comparison_request':ComparisonRequest(base=request,candidates=suggestions(request)).model_dump(mode='json')})
        else:
            if 'gas' in goals and has_amount:
                outputs['gas']=execute('estimate_substrate_gas',{'advisor_request':request.model_dump(mode='json')},'gas')
            topics=[x for x in ['temperature','duration'] if x in goals]
            if topics:
                data=request.model_dump(mode='json')
                outputs['conditions']=execute('advise_substrate_conditions',{'advisor_request':data,'topics':topics},'conditions')
    failed=next((r for r in outputs.values() if r.get('status')=='error'),None)
    full=outputs.get('full');legacy=outputs.get('legacy');gas=outputs.get('gas');conditions=outputs.get('conditions',{})
    effective=(full or gas or {}).get('conditional_reference_case') or full or gas
    mix=(effective or {}).get('mixture');analysis=(effective or legacy or {}).get('decision_analysis');bio=(analysis or {}).get('biogas') or (effective or {}).get('biogas',{})
    methane=(mix or {}).get('additive_methane_reference_m3') or (legacy or {}).get('methane_potential_m3')
    sources=list({s.get('id',s.get('url')):s for result in outputs.values() for s in result.get('sources',[]) if s.get('url')}.values())
    if 'catalog' in outputs:
        profiles=[p for m in outputs['catalog']['materials'] if request is None or m['id'] in {c.material for c in request.components} for p in m['profiles']]
        sources=list({p['source']['id']:p['source'] for p in profiles}.values())
    sentences=[];thermal=None;timing=None
    if failed:sentences=[t('Не удалось проверить расчёт; предыдущий состав сохранён.','The calculation could not be verified; the previous inventory is retained.','Есеп тексерілмеді; алдыңғы құрам сақталды.')]
    elif not goals:
        if request:
            total=sum(c.quantity*{'kg':1,'g':.001,'t':1000}.get(c.unit,0) for c in request.components)
            label=(f'{total:g} '+t('кг','kg','кг')) if all(c.unit in {'kg','g','t'} for c in request.components) else ', '.join(f'{c.quantity:g} {c.unit}' for c in request.components)
            sentences=[t(f'Сохранил сырьё: {label}.',f'Inventory saved: {label}.',f'Шикізат сақталды: {label}.')]
            pending=Question(id='smart-goal',text=t('Что рассчитать: выход газа, температуру, срок или экономику?','What would you like to estimate: gas, temperature, duration or economics?','Нені есептейік: газ, температура, мерзім әлде экономика?'),options=[t('Выход газа','Gas yield','Газ шығымы'),t('Температуру','Temperature','Температура')],fields=['goal'])
        else:sentences=[t('Биогаз образуется при разложении органики без кислорода; его топливная часть — метан. Я могу помочь оценить сырьё, условия и экономику.','Biogas comes from oxygen-free decomposition of organic matter; methane is its fuel component. I can help assess feedstock, conditions and economics.','Биогаз органиканың оттегісіз ыдырауынан пайда болады; оның отындық бөлігі — метан. Шикізат, жағдай және экономиканы бағалауға көмектесемін.')]
    elif 'reactor' in goals:sentences=[t('Реактор пока не подключён: реальных показаний температуры и газа нет. Управление оборудованием отключено.','The reactor is not connected; no live temperature or gas readings are available. Hardware control is disabled.','Реактор қосылмаған: температура мен газдың нақты көрсеткіші жоқ. Жабдықты басқару өшірілген.')]
    elif not request:sentences=[t('Укажите вид сырья, чтобы подобрать сопоставимые данные.','Please identify the substrate so I can use comparable evidence.','Сәйкес деректерді таңдау үшін шикізат түрін көрсетіңіз.')]
    else:
        if edit_plan:
            sentences.append(t('Условная смесь обновлена; подтверждённое наличие сохранено.' if state.active_mixture_scenario else 'Состав обновлён.', 'What-if blend updated; confirmed inventory is unchanged.' if state.active_mixture_scenario else 'Composition updated.', 'Шартты қоспа жаңартылды; расталған қор сақталды.' if state.active_mixture_scenario else 'Құрам жаңартылды.'))
        if 'gas' in goals:
            if not has_amount:sentences.append(t('Укажите количество сырья в килограммах или литрах, чтобы оценить газ.','Please provide kilograms or litres of feedstock to estimate gas.','Газды бағалау үшін шикізат мөлшерін килограмм не литрмен көрсетіңіз.'))
            elif methane:
                gas_value=span(bio.get('potential_biogas_m3'),'м³' if language!='en' else 'm³')
                if gas_value:
                    fraction=bio['methane_fraction'];pct=span({'low':fraction['low']*100,'high':fraction['high']*100},'%',0)
                    sentences.append(t(f'Условный ориентир: {gas_value} биогаза при {pct} метана; сам метан — {span(methane,"м³")}.',f'A conditional reference is {gas_value} biogas at {pct} methane; methane itself is {span(methane,"m³")}.',f'Шартты баға: {pct} метан үлесімен {gas_value} биогаз; метанның өзі {span(methane,"м³")}.'))
                else:sentences.append(t(f'Сумма отдельных оценок даёт {span(methane,"м³")} метана; общий биогаз требует измеренной доли метана.',f'The component estimates sum to {span(methane,"m³")} methane; total biogas needs a measured methane fraction.',f'Жеке бағалар қосындысы {span(methane,"м³")} метан; жалпы биогаз үшін метан үлесі қажет.'))
                sentences.append(t('Это расчётный ориентир, а не обещание реального сбора; для смеси взаимодействие компонентов не проверено.' if len(request.components)>1 else 'Это расчётный ориентир для сопоставимого сырья, а не обещание реального сбора.', 'This is a reference calculation, not a guaranteed plant yield; mixture interactions remain unverified.' if len(request.components)>1 else 'This is a reference for comparable feedstock, not guaranteed collected gas.', 'Бұл — есептік бағалау, нақты жиналатын газға кепілдік емес; қоспадағы өзара әсер тексерілмеген.' if len(request.components)>1 else 'Бұл — ұқсас шикізат үшін есептік баға, нақты газға кепілдік емес.'))
                if gas_value:sentences[-1]=sentences[-1].rstrip('.')+t('; Метан уже входит в общий объём.','; methane is already part of the total.','; метан жалпы көлемге кіреді.')
                if request.components[0].material=='manure':sentences[-2]=t('Если это жижа КРС: ','If this is cattle slurry: ','Егер бұл сиырдың сұйық көңі болса: ')+sentences[-2]
                if mix and any(c['assumptions'] for c in mix['components']):
                    assumed={c['material'] for c in mix['components'] if any('Material state is assumed' in a for a in c['assumptions'])}
                    if assumed:
                        descriptions=[t('навоз сопоставим с исследованной жижей КРС','manure matches the studied cattle slurry','көң зерттелген сиырдың сұйық көңіне ұқсас')] if assumed&{'cattle_manure','manure'} else []
                        if 'food_waste' in assumed:descriptions.append(t('пищевые отходы — с измельчённой пищевой пульпой','food waste matches prepared food pulp','тағам қалдығы ұсақталған пульпаға ұқсас'))
                        if descriptions:sentences[-1]=t('Оценка предполагает: ','This assumes: ','Бағалау мынаны болжайды: ')+', '.join(descriptions)+t('; реальный сбор и взаимодействие смеси не подтверждены.','; collected yield and blend interactions are unverified.','; нақты шығым мен қоспаның өзара әсері расталмаған.')+(t(' Метан уже входит в общий объём.',' Methane is already part of total biogas.',' Метан жалпы биогазға кіреді.') if gas_value else '')
            else:
                subtotal=span((mix or {}).get('known_component_additive_subtotal_m3'),'м³')
                sentences.append(t('Полный выход пока не рассчитан'+(f': известные части дают {subtotal} метана, но это не нижняя граница выхода смеси.' if subtotal else ': не хватает подходящих характеристик сырья.'),'The complete yield is unknown'+(f'; known parts give {subtotal} methane, which is not a lower bound for the mixture.' if subtotal else '; comparable substrate properties are missing.'),'Толық шығым есептелмеді: шикізаттың сәйкес қасиеттері жеткіліксіз.'))
                sentences.append(t('Следующий шаг — измерить состав или провести лабораторное испытание неподтверждённого компонента.','Next, measure the composition or assay the unsupported component.','Келесі қадам — құрамды өлшеу немесе расталмаған компонентті зертханада сынау.'))
        thermal=conditions.get('temperature') or (full or {}).get('temperature')
        if 'temperature' in goals:
            candidate=(thermal or {}).get('candidate');materials={c.material for c in request.components}
            geometry=conditions.get('geometry') or (analysis or {}).get('feasibility',{})
            if geometry.get('status') in {'PHYSICALLY_INFEASIBLE','REQUIRES_SAFETY_REVIEW'}:sentence=t('Сначала нужна проверка загрузки и геометрии реактора; назначать температурный режим для этих условий пока нельзя.','First review reactor loading and geometry; a temperature setpoint cannot yet be assigned for these conditions.','Алдымен реактор жүктемесі мен геометриясын тексеру керек; бұл шарттарға температура режимін әзірше белгілеуге болмайды.')
            elif candidate:sentence=t(f'Для заявленных условий можно рассмотреть {candidate["temperature_c"]:g} °C после инженерной проверки.',f'For the declared conditions, consider {candidate["temperature_c"]:g} °C after engineering review.',f'Берілген шарттарда инженерлік тексеруден кейін {candidate["temperature_c"]:g} °C қарастыруға болады.')
            elif materials=={'cattle_manure'} and all(c.material_state in {'slurry','unknown'} for c in request.components):sentence=t('Для мезофильного сбраживания жижи КРС ориентиром служит изученный режим около 35 °C; это не подтверждённый оптимум вашей установки.','A studied mesophilic reference for cattle slurry is about 35 °C; it is not a confirmed optimum for your reactor.','Сиырдың сұйық көңі үшін зерттелген мезофильді бағдар — шамамен 35 °C; бұл реакторыңыздың расталған оңтайлы режимі емес.')
            elif (thermal or {}).get('studies'):sentence=t('Сходные смеси исследовали при 35 °C, но это условие опыта, а не готовая настройка вашего реактора.','Related blends were studied at 35 °C; that is an experimental condition, not a ready reactor setpoint.','Ұқсас қоспалар 35 °C-та зерттелген; бұл тәжірибе шарты, реактордың дайын баптауы емес.')
            else:sentence=t('Для этого материала подходящая температура пока не подтверждена; нужен сопоставимый процесс или опыт.','No suitable temperature is established for this material; a comparable process or experiment is needed.','Бұл шикізатқа сәйкес температура расталмаған; ұқсас үдеріс немесе тәжірибе қажет.')
            sentences.append(sentence)
            if len(goals)==1:sentences.append(t('Количество влияет на нагрев и загрузку; режим выбирают с учётом состояния сырья и адаптации инокулята.','Amount affects heating and loading; material state and inoculum adaptation guide the biological regime.','Мөлшер жылыту мен жүктеуге әсер етеді; режим шикізат күйі мен инокуляттың бейімделуіне байланысты.'))
        timing=conditions.get('duration') or (full or {}).get('duration')
        if 'duration' in goals:
            hrt=(timing or {}).get('estimated_hrt_from_declared_feed_days')
            if hrt:sentences.append(t(f'Расчётное удерживание жидкости — {span(hrt,"суток")}; это не срок запуска или завершения партии.',f'Declared-flow hydraulic retention is {span(hrt,"days")}; this is not start-up or batch completion time.',f'Берілген ағын бойынша сұйықтықты ұстау — {span(hrt,"тәулік")}; бұл іске қосу не партияның аяқталу мерзімі емес.'))
            else:
                days=sorted({v for study in (timing or {}).get('studies',[]) if study['kind']=='BMP_INCUBATION' for v in study['days']})
                label='/'.join(str(x) for x in days)
                sentences.append(t(f'Срок вашей партии пока неизвестен: {label} суток в источниках — длительность лабораторных испытаний, а не универсальный срок работы реактора.' if days else 'Срок вашей партии пока неизвестен; для него нужен сопоставимый опыт или проверенная кинетическая модель.',f'Your batch duration is unknown: source assays lasting {label} days are not universal reactor operating times.' if days else 'Your batch duration is unknown; a comparable experiment or validated kinetic model is needed.',f'Партияңыздың мерзімі белгісіз: {label} тәулік — зертханалық сынақ, реактордың әмбебап жұмыс мерзімі емес.' if days else 'Партия мерзімі белгісіз; ұқсас тәжірибе немесе тексерілген кинетикалық модель қажет.'))
        if 'economics' in goals or 'compare' in goals:
            decision=(analysis or {}).get('decision',{});selected=next((r for r in (analysis or {}).get('scenarios',[]) if r['id']==decision.get('selected_scenario')),None)
            net=(selected or {}).get('net_result_kzt');budget=(selected or {}).get('break_even',{}).get('maximum_total_processing_cost_to_match_sale_kzt')
            if net:sentences.append(t(f'В заданном сравнении чистый результат выбранного варианта — {span(net,"₸")}; это расчёт по указанным ценам и затратам.',f'The selected scenario gives {span(net,"KZT")} net under the declared prices and costs.',f'Берілген баға мен шығын бойынша таңдалған нұсқаның таза нәтижесі — {span(net,"₸")}.'))
            elif budget:sentences.append(t(f'Переработка может превысить ценовой ориентир продажи, если все её затраты ниже {span(budget,"₸")}; гарантированной прибыли пока нет.',f'Processing can beat the sale reference below the total-cost threshold {span(budget,"KZT")}; profit is not guaranteed.',f'Барлық шығын {span(budget,"₸")} шегінен төмен болса, өңдеу сату бағдарынан тиімді болуы мүмкін; пайдаға кепілдік жоқ.'))
            else:sentences.append(t('Пока нельзя обоснованно выбрать продажу или переработку: нужны применимая цена покупателя и полные расходы установки.','Selling versus processing cannot yet be decided: an eligible buyer quote and complete plant costs are needed.','Сату не өңдеуді таңдау әзірше негізделмеген: сатып алушы бағасы мен толық шығын қажет.'))
            reference=(legacy or {}).get('catalog_reference_value_kzt')
            if reference:sentences.append(t(f'Каталожный ориентир сырья — {span(reference,"₸")}, не подтверждённый доход.',f'The feedstock asking reference is {span(reference,"KZT")}, not confirmed revenue.',f'Шикізаттың каталогтық бағасы — {span(reference,"₸")}, расталған табыс емес.'))
            if outputs.get('comparison'):sentences.append(t('Составы сравнены в пределах наличия; оптимальная смесь без проверки взаимодействия не объявляется.','Blends were compared within inventory; no optimum is claimed without interaction evidence.','Құрамдар қор шегінде салыстырылды; өзара әсер тексерілмей оңтайлы қоспа жарияланбайды.'))
        if 'loading' in goals:sentences.append(t('Загрузить всё сразу пока нельзя рекомендовать: полный объём не равен рабочему, нужны фактический объём смеси и занятое инокулятом пространство.','A full single charge cannot yet be recommended: total capacity is not working volume; mixture and inoculum volumes are needed.','Барлығын бірден жүктеу әзірше ұсынылмайды: толық көлем жұмыс көлеміне тең емес, қоспа мен инокулят көлемі қажет.'))
    form_reply=bool(re.fullmatch(r'\s*(?:навозная жижа|с подстилкой|cattle slurry|сұйық көң)[.!]?\s*',text,re.I))
    if form_reply and methane and goals==['gas'] and not plan['detail'] and not plan['one_sentence']:
        sentences=[t(f'Уточнение сохранено; ориентир метана для сопоставимого сырья — {span(methane,"м³")}, фактический сбор не гарантирован.',f'Form saved; the methane reference for comparable material is {span(methane,"m³")}, not guaranteed collected gas.',f'Күйі сақталды; ұқсас шикізаттың метан бағасы — {span(methane,"м³")}, нақты газға кепілдік жоқ.')]
    if plan['detail']:
        if mix and 'gas' in goals:
            for c in mix['components']:sentences.append(t(f"{catalog.name(c['material'])}: влажная масса {span(c['wet_mass_kg'],'кг') or 'неизвестна'}, отдельный ориентир метана {span(c['methane_reference_m3'],'м³') or 'не установлен'}.",f"{catalog.name(c['material'],'en')}: wet mass {span(c['wet_mass_kg'],'kg') or 'unknown'}, separate methane reference {span(c['methane_reference_m3'],'m³') or 'unknown'}.",f"{catalog.name(c['material'],'kk')}: ылғал масса {span(c['wet_mass_kg'],'кг') or 'белгісіз'}, жеке метан бағасы {span(c['methane_reference_m3'],'м³') or 'белгісіз'}."))
            sentences.append(t('Формула: масса органического вещества × лабораторный потенциал ÷ 1000 даёт м³ метана при согласованных газовых условиях; покрытие границ не проверено.','Formula: organic solids mass × laboratory methane potential ÷ 1000 gives m³ methane at compatible gas conditions; interval coverage is unverified.','Формула: органикалық зат массасы × зертханалық әлеует ÷ 1000 — газ шарттары сәйкес болғандағы метанның м³ көлемі; шектердің қамтуы тексерілмеген.'))
        if analysis and 'economics' in goals:sentences.append(t('Неизвестные расходы не считаются нулём; тепло и электричество — альтернативы одного газа, а рыночная цена природного газа не оценивает сырой биогаз.','Unknown costs are not zero; heat and electricity are alternatives from one gas stream, and natural-gas prices do not value raw biogas.','Белгісіз шығын нөл емес; жылу мен электр бір газ ағынының баламалары, табиғи газ бағасы шикі биогазды бағаламайды.'))
        if thermal and 'temperature' in goals:sentences.append(t('В источниках различаются непрерывные CSTR при 35/50 °C и испытания смесей при 35 °C; перенос требует сопоставимых сырья, инокулята и контроля.','Sources distinguish continuous CSTR studies at 35/50 °C from mixture assays at 35 °C; transfer needs matched feedstock, inoculum and control.','Дереккөздердегі 35/50 °C үздіксіз CSTR мен 35 °C қоспа сынақтары бөлек; тасымалдау үшін шикізат, инокулят және бақылау сәйкес болуы тиіс.'))
    if plan.get('source_only'):
        pending=None;sentences=[t('Ссылки на первичные источники этого результата приведены ниже; их параметры относятся к исследованным образцам, а не измерениям вашей партии.','Primary sources for this result are linked below; their properties describe studied samples, not measurements of your batch.','Осы нәтиженің бастапқы дереккөздеріне сілтемелер төменде; мәндер сіздің партияға емес, зерттелген үлгілерге жатады.')] if sources else [t('Подходящего проверенного источника для этого сырья пока нет; нужны идентификация материала и проверка первичной статьи.','No suitable verified source is available for this material; identify it and review a primary study first.','Бұл шикізат үшін сәйкес тексерілген дереккөз жоқ; материалды анықтап, бастапқы мақаланы тексеру қажет.')]
    if plan['one_sentence']:sentences=[re.sub(r'[.!?]\s+','; ','; '.join(x.rstrip('.!?') for x in sentences[:2])).rstrip('.!?')+'.'] if sentences else []
    elif not plan['detail']:sentences=sentences[:5]
    body=' '.join(sentences)
    state.pending_question=pending
    if goals:state.smart_goals=list(goals)
    if outputs:state.smart_cache['last']={'signature':signature,'goals':list(goals),'outputs':copy.deepcopy(outputs),'at':utcnow().isoformat()}
    agent.history=(agent.history+[text])[-8:];agent.last_pending=[]
    metadata={'smart_version':'7.7','intent_plan':plan,'cache_hits':cache_hits,'tool_calls':trace,'smart_result':outputs,'component_inventory':state.mixture_components,'scenario_inventory':state.mixture_scenario_components,
              'extracted_entities':extraction.model_dump(),'confirmed_parameters':{k:f.model_dump() for k,f in state.facts.items() if f.provenance=='USER_CONFIRMED'},'llm_proposal':proposal.model_dump() if proposal else None,'latency_seconds':time.perf_counter()-started}
    if legacy:metadata['research_result']=legacy
    elif gas:metadata['research_result']={'result_level':(mix or {}).get('result_level'),'methane_potential_m3':methane}
    elif full:metadata['research_result']=full
    if full:metadata['advisor_result']=full
    return {'conversation_version':'7','analysis_version':'7.5' if legacy else '7.6','smart_agent_version':'7.7','mode':'llm_tools' if proposal else 'deterministic_tools_no_llm','answer':body,
      'user_facing_answer':{'paragraphs':[body],'sections':[],'question':pending.model_dump() if pending else None,'sources':sources,'modes':['show_sources'] if plan.get('source_only') else [],'assumptions':[]},'tools':trace,'provider_status':list(agent.llm.status),'missing':[],
      'context':dict(agent.context),'context_updated':True,'memory':state.model_dump(mode='json',exclude={'smart_cache'}),'pending_question':pending.model_dump() if pending else None,'technical_metadata':metadata,'actuator_access':False}
