"""Persistent task graph and independent material axes over the preserved agent.

Only literal, independently parsed facts enter inventory. The local LLM proposes
intent interpretation; Python plans tools, calculates, and synthesizes numbers.
"""
import copy,hashlib,json,re,time,uuid
from src.advisor import catalog
from src.advisor.material_axes import extract,normalize,ANIMALS
from src.advisor.schemas import AdvisorRequest,Component
from src.agent import mixture_parser
from src.agent.dialogue_types import Question
from src.agent.dialogue_memory import fact
from src.market.domain import utcnow

def clean(text):
    for wrong,right in [('коровего','коровьего'),('навз','навоз'),('подстилкй','подстилкой'),('электричство','электричество'),('раcсчитай','рассчитай'),('литорв','литров')]:text=re.sub(wrong,right,text,flags=re.I)
    return text

def applicable(text,state):
    if text.lstrip().startswith('{'):
        try:return bool(state.advanced and 'mixture_components' in json.loads(text))
        except ValueError:return False
    if re.search(r'\bmae\b|точность.*модел|какая.*модель|model info|истори\w*\s+цен|показани\w*\s+реактор|статус\s+реактор',text,re.I):return False
    if state.advanced:return True
    try:explicit=mixture_parser.explicit_components(clean(text))
    except ValueError:explicit=[]
    if explicit and goals_in(clean(text)) and any(c.material.endswith('_manure') and c.physical_state=='unknown' for c in explicit):return True
    return bool(re.search(r'подстил|bedded|dry.*manure|сух\w*.*(?:навоз|пом[её]т)|(?:навоз|пом[её]т).*сух|перепрев|компостирован|переведи|пересчит.*(?:литр|килограмм)|convert|мл\b|millilit',clean(text),re.I))

def goals_in(text):
    patterns={'gas':r'газ|метан|bmp|gas|methane','heat':r'тепл|heat','electricity':r'электр|electric','economics':r'затрат|стоим|стоит|выгод|прибыл|продать|продаж|cost|profit|sell','temperature':r'температур|градус|temperature','duration':r'дней|суток|срок|долго|длитель|days|how long','conversion':r'переведи|перевест|пересчит.*(?:литр|килограмм)|convert'}
    return [g for g,p in patterns.items() if re.search(p,text,re.I)]

def seed(state):
    if state.mixture_components:return copy.deepcopy(state.mixture_components)
    if state.value('material') and state.value('quantity'):
        try:return [Component(id='c1',material=catalog.normalized(state.value('material')),quantity=state.value('quantity'),unit=state.value('unit','kg'),material_state=state.value('material_state','unknown')).model_dump(mode='json')]
        except ValueError:pass
    return []

def parse(text,state,d):
    if text.lstrip().startswith('{'):
        raw=json.loads(text)
        if set(raw)-{'mixture_components','decision_inputs','advisor_inputs','language'}:raise ValueError('Unknown structured dialogue fields')
        overrides={**d.get('request_overrides',{}),**raw.get('advisor_inputs',{})}
        validated=AdvisorRequest(components=raw['mixture_components'],**overrides)
        d['inventory']=[c.model_dump(mode='json') for c in validated.components];d.pop('scenario',None);d['active_scenario']=False;d['request_overrides']=overrides
        d.setdefault('history',[]).append({'at':utcnow().isoformat(),'message':'Explicit structured inventory update','components':copy.deepcopy(d['inventory']),'scenario':False})
        return True,False
    current=[Component.model_validate(c) for c in d.get('scenario',d.get('inventory',seed(state)))];axes=extract(text)
    new_batch=bool(re.search(r'новая партия|новая задача|другая партия|new batch|start over',text,re.I))
    if new_batch:
        current=[];d['inventory']=[];d.pop('scenario',None);d['active_scenario']=False
    candidates=mixture_parser.explicit_components(text)
    amounts=mixture_parser.amounts(text);used_amounts=set()
    for index,c in enumerate(candidates):
        # Scope properties to this component, excluding neighbouring quantities.
        bound=next((a for a in amounts if a['start'] not in used_amounts and a['value']==c.quantity and a['unit']==c.unit and catalog.matches(text[a['end']:min(len(text),a['end']+90)])),None)
        if bound:
            used_amounts.add(bound['start'])
            end=next((a['start'] for a in amounts if a['start']>bound['start']),len(text))
            segment=text[bound['start']:end]
        else:segment=c.evidence
        local=extract(segment)
        for k,v in local.items():setattr(c,k,v)
        normalize(c)
    addition=bool(re.search(r'добав|\badd\b',text,re.I));hypothesis=bool(re.search(r'\bесли\b|what if|допустим',text,re.I))
    changed=False
    inventory_edit=bool(re.search(r'убери|убрать|удали|исключи|замени|вдвое|remove|replace|double',text,re.I))
    if inventory_edit and current:
        temporary=state.model_copy(deep=True);temporary.mixture_components=[c.model_dump(mode='json') for c in current]
        edit=mixture_parser.parse_turn(text,temporary)
        if not edit:raise ValueError('Уточните материал и изменение количества')
        current=edit['components'];changed=True
    elif candidates:
        if addition and current:
            for c in candidates:
                c.id='c'+uuid.uuid4().hex[:8];current.append(c)
        else:current=candidates
        changed=True
    elif current and state.pending_question and state.pending_question.id=='advanced-material-state' and (form:=mixture_parser.state_of(text))!='unknown' and len(text.split())<=8:
        # A short answer to the pending form question belongs to that one
        # component. Component normalization keeps legacy and physical axes aligned.
        target_id=None
        if state.pending_question and state.pending_question.id=='advanced-material-state':
            match=re.search(r'\b(c[a-z0-9_-]+)\b',state.pending_question.text,re.I)
            if match:target_id=match.group(1)
        targets=[c for c in current if c.id==target_id] if target_id else current if len(current)==1 else []
        if len(targets)==1:
            targets[0].material_state=form
            changed=True
    elif current and axes:
        hits={h['material'] for h in catalog.matches(text)}
        selected=[c for c in current if c.material in hits or c.material=='manure' and axes.get('animal') or not hits and len(current)==1]
        if len(selected)!=1:raise ValueError('Уточните, к какому компоненту относится изменение состояния')
        c=selected[0]
        for k,v in axes.items():setattr(c,k,v)
        if axes.get('animal'):c.material=ANIMALS[axes['animal']]
        normalize(c);changed=True
    elif current:
        quantities=mixture_parser.amounts(text)
        if quantities and not re.search(r'реактор|плотност',text,re.I):
            if len(current)!=1:raise ValueError('Укажите материал, количество которого меняется')
            current[0].quantity=quantities[0]['value'];current[0].unit=quantities[0]['unit'];changed=True
    if changed:
        current=[Component.model_validate(c.model_dump()) for c in current]
        serialized=[c.model_dump(mode='json') for c in current]
        if hypothesis:
            d['scenario']=serialized;d['active_scenario']=True
        else:
            # A direct edit after a what-if continues that branch, without
            # converting hypothetical stock into confirmed inventory.
            if d.get('active_scenario') and not new_batch and not candidates or d.get('active_scenario') and addition:
                d['scenario']=serialized
            else:d['inventory']=serialized;d.pop('scenario',None);d['active_scenario']=False
        d.setdefault('history',[]).append({'at':utcnow().isoformat(),'message':text,'components':serialized,'scenario':bool(d.get('active_scenario'))});d['history']=d['history'][-60:]
    if new_batch:
        d.pop('task',None);d.pop('last_goals',None);d.pop('last_calculation_goals',None);d['reactor']={};d.pop('last_results',None);d.pop('cache',None);d.pop('request_overrides',None)
    # Vessel amounts never become substrate amounts.
    reactor_pattern=r'(?:реактор\w*|reactor\w*|digester\w*)\s*(?:(?:на|объ[её]м\w*|вместимост\w*|capacity(?:\s+of)?|[:=])\s*)?('+mixture_parser.NUMBER+r')\s*('+mixture_parser.UNIT+r')'
    match=re.search(reactor_pattern,text,re.I)
    if not match:match=re.search(r'('+mixture_parser.NUMBER+r')\s*('+mixture_parser.UNIT+r')\s*(?:реактор\w*|reactor\w*|digester\w*)\b',text,re.I)
    if match:
        from src.advisor.mixing import FACTORS
        family,factor=FACTORS[mixture_parser.unit(match[2])]
        if family!='volume':raise ValueError('Объём реактора нужно указать в единицах объёма')
        d.setdefault('reactor',{})['total_volume_l']=float(match[1].replace(',','.'))*factor
    # Literal measured density only; missing density never becomes 1 kg/L.
    density=re.search(r'плотност\w*\s*(?:измерен\w*\s*)?[:=]?\s*(\d+(?:[.,]\d+)?)\s*кг\s*/\s*л\b',text,re.I)
    if density and len(current)==1:
        from src.economics.decision_schemas import Range
        hypothetical_density=bool(re.search(r'условн|допустим|предполож|assum',text,re.I))
        value=float(density[1].replace(',','.'));current[0].properties.density_kg_l=Range(low=value,high=value,provenance='HYPOTHETICAL_SCENARIO' if hypothetical_density else 'USER_REPORTED',evidence=density[0])
        current=[Component.model_validate(c.model_dump()) for c in current]
        d['scenario' if d.get('active_scenario') else 'inventory']=[c.model_dump(mode='json') for c in current];changed=True
    return changed,new_batch

def request_for(state,d):
    data={'components':d.get('scenario') if d.get('active_scenario') else d.get('inventory',seed(state)),'assume_common_dry_gas_basis':True,'decision':state.decision_settings,'reactor_total_volume_l':d.get('reactor',{}).get('total_volume_l',state.value('reactor_total_volume_l')),'region':state.value('market_region','KZ-Karaganda'),'region_confirmed':bool(state.value('region_confirmed',False)),'online':False}
    data.update(d.get('request_overrides',{}));data['online']=False
    return AdvisorRequest.model_validate(data)

def span(v,unit='',digits=1):
    if not v:return None
    return (f"{v['low']:.{digits}f}" if abs(v['high']-v['low'])<10**(-digits) else f"{v['low']:.{digits}f}–{v['high']:.{digits}f}")+(('' if unit=='%' else ' ')+unit if unit else '')

def respond(agent,original):
    started=time.perf_counter();text=clean(original);state=agent.state.model_copy(deep=True);d=copy.deepcopy(state.advanced);d.setdefault('inventory',seed(state));d.setdefault('preferences',{});trace=[]
    from src.agent.nlu import language_of
    state.language=language_of(original,state.language)
    if re.fullmatch(r'\s*(?:спасибо|благодарю|понятно|thanks|thank you)[!.\s]*',text,re.I):return reply(agent,state,original,['Пожалуйста; состав и расчёты сохранены для продолжения.'],[],started)
    prior_goals=d.get('task',{}).get('goals',d.get('last_goals',[]));explicit=[] if text.lstrip().startswith('{') else goals_in(text)
    density_why=bool(re.search(r'почему.*плотност|why.*density',text,re.I));one=bool(re.search(r'одним предложением|one sentence',text,re.I));detail=bool(re.search(r'подроб|формул|detail',text,re.I));simple=bool(re.search(r'простыми|проще|simply',text,re.I))
    if one:d['preferences']['format']='one_sentence'
    elif detail:d['preferences']['format']='detailed'
    elif simple:d['preferences']['format']='simple'
    try:changed,new_batch=parse(text,state,d)
    except (ValueError,TypeError) as exc:
        return reply(agent,agent.state,original,[str(exc)],[],started,pending=None,updated=False)
    if new_batch:
        state.facts={k:v for k,v in state.facts.items() if k in {'model','market_region'}};state.derived={};state.estimates={};state.assumptions={k:v for k,v in state.assumptions.items() if k=='market_region'}
    from src.agent import decision_bridge
    state.decision_settings=decision_bridge.propose(text,state,new_batch)
    state.mixture_components=copy.deepcopy(d.get('inventory',[]))
    state.mixture_scenario_components=copy.deepcopy(d.get('scenario',[]))
    state.active_mixture_scenario=bool(d.get('active_scenario',False))
    if not d.get('active_scenario'):
        components=d.get('inventory',[])
        if len(components)==1:
            component=components[0]
            evidence=component.get('evidence') or 'Confirmed substrate inventory'
            state.facts['material']=fact(component['material'],provenance='USER_CONFIRMED',evidence=evidence)
            state.facts['quantity']=fact(component['quantity'],component['unit'],provenance='USER_CONFIRMED',evidence=evidence)
            state.facts['unit']=fact(component['unit'],provenance='USER_CONFIRMED',evidence=evidence)
            if component.get('material_state')!='unknown':state.facts['material_state']=fact(component['material_state'],provenance='USER_CONFIRMED',evidence=evidence)
            else:state.facts.pop('material_state',None)
            if component['unit'] in {'L','mL','m3'}:
                factor={'L':1,'mL':.001,'m3':1000}[component['unit']]
                state.facts['material_volume_l']=fact(component['quantity']*factor,'L',provenance='CALCULATED_FROM_CONFIRMED',evidence='Unit conversion from confirmed component quantity')
                state.facts.pop('mass_kg',None)
            elif component['unit'] in {'kg','g','t'}:
                factor={'kg':1,'g':.001,'t':1000}[component['unit']]
                state.facts['mass_kg']=fact(component['quantity']*factor,'kg',provenance='CALCULATED_FROM_CONFIRMED',evidence='Unit conversion from confirmed component quantity')
                state.facts.pop('material_volume_l',None)
        elif len(components)>1:
            for key in ['material','quantity','unit','material_state','mass_kg','material_volume_l']:
                state.facts.pop(key,None)
        reactor_total=d.get('reactor',{}).get('total_volume_l')
        if reactor_total is not None:state.facts['reactor_total_volume_l']=fact(reactor_total,'L',provenance='USER_CONFIRMED',evidence='Explicit reactor capacity')
        elif new_batch:state.facts.pop('reactor_total_volume_l',None)
    # The LLM is useful on fresh/composite requests. Literal clarifications and
    # format/quantity follow-ups run without another generation.
    initial=not agent.state.advanced or new_batch
    proposal=None
    source_only=bool(re.search(r'источник|откуда.*(?:числ|данн)|sources',text,re.I))
    needs_interpretation=initial or not explicit and not changed and not any([density_why,one,detail,simple,source_only]) and not state.pending_question
    if needs_interpretation and hasattr(agent.llm,'interpret'):proposal=agent.llm.interpret(original,state.brief())
    else:agent.llm.status=[]
    goals=explicit or prior_goals
    if not goals and changed:goals=['gas']
    if new_batch and not explicit:goals=['gas']
    if proposal and not explicit and not changed:
        mapping={'methane_yield':['gas'],'temperature_recommendation':['temperature'],'economic_comparison':['economics'],'process_guidance':['temperature','duration']}
        interpreted=list(dict.fromkeys(g for i in proposal.intents for g in mapping.get(i,[])))
        if interpreted:goals=interpreted
    if not d.get('task') or explicit or new_batch:d['task']={'id':uuid.uuid4().hex,'original_text':original,'goals':goals,'status':{g:'pending' for g in goals}}
    parameter_edit=bool(re.search(r'КПД|извлечени|доля\s+метана|efficiency|recovery',text,re.I))
    if (changed or parameter_edit) and not explicit and d.get('last_calculation_goals'):goals=d['last_calculation_goals']
    d['last_goals']=goals
    if any(g in goals for g in ['gas','heat','electricity','economics']):d['last_calculation_goals']=goals
    state.advanced=d;pending=None;sentences=[];outputs={}
    try:r=request_for(state,d)
    except ValueError:r=None
    unknown=next((c for c in r.components if c.material=='manure' and c.animal=='unknown'),None) if r else None
    if unknown:
        pending=Question(id='advanced-species',text='Это коровий, свиной, птичий или другой навоз?',fields=['animal'],options=['Коровий','Свиной','Птичий'],reason='Resume all original tasks after species clarification')
        sentences=['Сохранил количество сырья, реактор и все задачи расчёта.'];d['task']['status']={g:'awaiting_species' for g in goals}
    elif r and (unknown_form:=next((c for c in r.components if c.material.endswith('_manure') and c.physical_state=='unknown'),None)):
        choices=['Жидкая жижа','Полужидкое','Твёрдое','Сухое','С подстилкой']
        pending=Question(id='advanced-material-state',text=f"Какое физическое состояние у компонента {unknown_form.id}: жидкое, полужидкое, твёрдое, сухое или с подстилкой?",fields=['physical_state'],options=choices,reason='Select a supported physical form before matching literature profiles')
        sentences=['Вид животного определён, но состояние навоза неизвестно. Профиль, плотность и выход нельзя выбирать без этой характеристики.'];d['task']['status']={g:'awaiting_material_state' for g in goals}
    elif r is None:sentences=['Укажите сырьё и его количество, чтобы продолжить расчёт.']
    else:
        state.mixture_components=copy.deepcopy(d['inventory']);state.mixture_scenario_components=copy.deepcopy(d.get('scenario',[]));state.active_mixture_scenario=d.get('active_scenario',False)
        r=request_for(state,d)
        from src.advisor.conversion import document
        evidence=hashlib.sha256(json.dumps(catalog.document(),sort_keys=True).encode()).hexdigest()
        def execute(name,ctx,key):
            inputs=copy.deepcopy(ctx)
            if key=='conditions':
                for c in inputs['advisor_request']['components']:c['quantity']=1
                inputs['advisor_request']['reactor_total_volume_l']=None
            if key=='gas':
                inputs['advisor_request']['decision']={};inputs['advisor_request']['reactor_total_volume_l']=None;inputs['advisor_request']['region']=''
            signature=hashlib.sha256(json.dumps({'input':inputs,'evidence':evidence},sort_keys=True).encode()).hexdigest();cache=d.setdefault('cache',{}).get(key,{})
            # Prices are resolved anew on an economic question, including age.
            hit=key!='economics' and cache.get('signature')==signature
            result=copy.deepcopy(cache['result']) if hit else agent.registry.execute(name,ctx,{},text)
            if result['status']=='error':raise ValueError(result['message'])
            if key in {'gas','conditions'}:
                from src.advisor.focused import geometry_for
                result['geometry']=geometry_for(r)
            json.dumps(result,allow_nan=False);trace.append({'tool':name,'status':result['status'],'cache_hit':hit,'input_origin':'literal_facts_and_explicit_reference_scenarios','result':result})
            d['cache'][key]={'signature':signature,'result':result};return result
        ctx={'advisor_request':r.model_dump(mode='json')}
        reuse_format=(one or simple or detail or density_why or source_only) and not changed and not explicit
        if reuse_format and d.get('last_results'):outputs=copy.deepcopy(d['last_results'])
        else:
            if 'conversion' in goals:
                target='mL' if re.search(r'миллилитр|мл\b|\bml\b',text,re.I) else 'L' if re.search(r'литр|\bл\b|lit[er]',text,re.I) else 'm3' if re.search(r'м³|м3|m3',text,re.I) else 'g' if re.search(r'грамм|\bг\b',text,re.I) and not re.search(r'килограмм',text,re.I) else 't' if re.search(r'тонн|\bт\b',text,re.I) else 'kg'
                outputs['conversion']=execute('convert_substrate_units',{**ctx,'target_unit':target},'conversion')
            if set(goals)&{'gas','heat','electricity','economics'}:
                outputs['gas']=execute('estimate_advanced_gas',ctx,'gas')
                if set(goals)&{'heat','electricity','economics'}:outputs['energy']=execute('estimate_advanced_energy',{**ctx,'mixture':outputs['gas']['mixture']},'energy')
                if 'economics' in goals:outputs['economics']=execute('evaluate_advanced_economics',{**ctx,'mixture':outputs['gas']['mixture']},'economics')
            if set(goals)&{'temperature','duration'}:outputs['conditions']=execute('get_matched_substrate_conditions',ctx,'conditions')
            d['last_results']=copy.deepcopy(outputs)
        sentences=synthesize(outputs,r,goals,density_why,detail)
        if source_only:sentences=['Первичные источники и рыночные ссылки приведены ниже; параметры публикаций описывают исследованные образцы, а допущения вашей партии сохранены отдельно.']
        if d.get('active_scenario') and changed:sentences.insert(0,'Расчёт для изменённого сценария; исходная партия сохранена.')
        gas=outputs.get('gas',{});mix=gas.get('mixture',{})
        d['assumptions']=gas.get('scenario_assumptions',[])
        d['sources']=gas.get('sources',[])
        for key,value in [('wet_mass_kg',mix.get('total_wet_mass_kg')),('methane_m3',mix.get('additive_methane_reference_m3'))]:
            if value is not None:state.estimates['advanced_'+key]=fact(value,provenance='ASSUMED_FOR_SCENARIO',evidence='Literature transfer / scenario, not measured plant output',dependencies=['advanced_inventory'])
            elif changed:state.estimates.pop('advanced_'+key,None)
        for g in goals:
            status='reference_calculated'
            if g=='gas' and not mix.get('additive_methane_reference_m3'):status='partial_missing_properties'
            if g=='economics' and not any(s.get('net_result_kzt') for s in outputs.get('economics',{}).get('decision_analysis',{}).get('scenarios',[])):status='partial_missing_costs_and_quotes'
            d['task']['status'][g]=status
        d['results']={k:{'calculated_at':utcnow().isoformat(),'kind':'CONDITIONAL_REFERENCE'} for k in outputs}
    tasks=d.setdefault('tasks',[])
    tasks=[task for task in tasks if task['id']!=d.get('task',{}).get('id')]
    if d.get('task'):tasks.append(copy.deepcopy(d['task']))
    d['tasks']=tasks[-60:];d['unfinished_tasks']=[{'id':task['id'],'original_text':task['original_text'],'goals':{g:s for g,s in task['status'].items() if s.startswith(('awaiting','partial'))}} for task in d['tasks'] if any(s.startswith(('awaiting','partial')) for s in task['status'].values())]
    state.pending_question=pending;state.smart_goals=goals;state.advanced=d
    if d.get('preferences',{}).get('format')=='simple' and not density_why and len(sentences)>3:
        sentences=[s for s in sentences if not s.startswith('Масса сырья')][:2]+[next((s for s in sentences if s.startswith('Чистая выгода')),sentences[-1])]
    if d.get('preferences',{}).get('format')=='one_sentence' and sentences:
        core=next((s for s in sentences if 'потенциал —' in s or 'лабораторный ориентир —' in s),sentences[0]);tail='чистая выгода пока неизвестна без предложения покупателя и всех затрат' if outputs.get('economics') else 'это условный ориентир, а не измеренная выработка'
        sentences=[core.rstrip('.')+'; '+tail+'.'] if not density_why else ['; '.join(s.rstrip('.') for s in sentences[:2])+'.']
    agent.state=state;agent.history=(agent.history+[original])[-8:]
    return reply(agent,state,original,sentences,trace,started,pending,outputs=outputs,proposal=proposal)

def synthesize(out,r,goals,density_why=False,detail=False):
    sentences=[];gas=out.get('gas',{});mix=gas.get('mixture',{});energy=out.get('energy',{});econ=out.get('economics',{}).get('decision_analysis',{})
    if density_why:
        rows=mix.get('components',[])
        densities=[row.get('properties_used',{}).get('density_kg_l') for row in rows]
        ds=[d for d in densities if d]
        if ds:return [f"Плотность {span(ds[0]['range'],'кг/л',3)} взята из {ds[0].get('locator') or ds[0].get('evidence') or 'указанного сценария'}; это не измерение вашей партии.",'Для подстилочного навоза использован отдельный справочник; навозная жижа им не заменялась.','Для точного пересчёта взвесьте известный объём без тары при таком же уплотнении.']
        return ['Для этой партии плотность не известна, поэтому объём не был выдуман.','Взвесьте известный объём без тары либо задайте явно условную плотность.']
    if 'conversion' in out:
        for c in out['conversion']['conversions']:
            density=c.get('density');description=f" при плотности {span(density,'кг/л',3)} ({'по вашим данным' if density['mode']=='MEASURED' else 'условный пример' if density['mode']=='ILLUSTRATIVE_ASSUMPTION' else 'литературный ориентир'})" if density else ''
            sentences.append(f"{catalog.name(c['material'])}: {span(c['value'],c['target_unit'])}{description}." if c.get('value') else f"{catalog.name(c['material'])}: объём неизвестен — нужна плотность именно этого состояния сырья.")
    if mix:
        mass=mix.get('total_wet_mass_kg');methane=mix.get('additive_methane_reference_m3');biogas=energy.get('biogas',gas.get('biogas',{}));bio=biogas.get('potential_biogas_m3')
        if mass:
            density=mix['components'][0].get('properties_used',{}).get('density_kg_l')
            suffix=f" при {span(density['range'],'кг/л',3)}" if density and len(r.components)==1 and r.components[0].unit in {'mL','L','m3'} else ''
            sentences.append(f"Масса сырья — около {span(mass,'кг')}{suffix}.")
        if methane:
            fraction=biogas.get('methane_fraction')
            pct=span({'low':fraction['low']*100,'high':fraction['high']*100},'%',0) if fraction else None
            sentences.append(f"Условный потенциал — {span(bio,'м³',2)} биогаза при {'условно принятых' if energy.get('methane_fraction_assumed',gas.get('methane_fraction_assumed')) else 'заданных'} {pct} метана, включая {span(methane,'м³',2)} метана." if bio else f"Расчётный лабораторный ориентир — {span(methane,'м³',2)} метана; общий биогаз требует подходящей доли метана.")
        else:
            partial=mix.get('known_component_additive_subtotal_m3')
            sentences.append(f"Известные компоненты отдельно дают ориентир {span(partial,'м³')} метана; полный выход смеси пока неизвестен." if partial else 'Полный выход газа пока неизвестен: для указанного состояния не хватает измеренных TS, VS, BMP или плотности.')
        assumptions=gas.get('scenario_assumptions',[])
        dry=any(c.physical_state=='dry' and c.material=='cattle_manure' for c in r.components)
        if dry and assumptions:
            row=next(row for row in mix['components'] if row['material']=='cattle_manure' and row['physical_state']=='dry');ts=row.get('properties_used',{}).get('ts_fraction',{}).get('range');ts_text=span({'low':ts['low']*100,'high':ts['high']*100},'%',0) if ts else 'неизвестной долей'
            sentences.append(f'Для сухого навоза показан только условный пример с {ts_text} сухого вещества и характеристиками органической части другого подстилочного образца; свежесть не меняет сухость.')
        elif assumptions:sentences.append('Это условный перенос между справочником плотности и отдельным опытом с опилочной подстилкой; состав подстилки и уплотнение вашей партии не измерены.')
        elif len(r.components)>1:sentences.append('Это сумма отдельных литературных ориентиров при условно совместимых объёмах газа; эффект совместного сбраживания не проверен.')
    values=energy.get('energy',{}).get('outputs',{})
    if values:
        params=energy['energy']['parameters']
        pct=lambda key:span({'low':params[key]['low']*100,'high':params[key]['high']*100},'%',0)
        sentences.append(f"При {'условном' if energy['energy']['assumed_parameters'] else 'заданном'} сборе {pct('recovery_fraction')} потенциала: {span(values.get('heat_only_kwh'),'кВт·ч')} тепла при КПД {pct('thermal_efficiency')} либо {span(values.get('electricity_only_kwh'),'кВт·ч')} электричества при КПД {pct('electrical_efficiency')}; это альтернативные способы использования одного газа до собственных затрат.")
    if econ:
        rows=econ.get('scenarios',[]);e=next((x for x in rows if x['id']=='C_electricity'),{});gross=e.get('gross_benefit_reference_kzt');price=econ.get('prices',{}).get('electricity',{})
        if gross:
            obs=price.get('observation',{});date=price.get('published_at') or obs.get('effective_from') or obs.get('published_at') or 'дата в источнике';age=price.get('age_days',obs.get('age_days'));stale='устаревший справочный' if obs.get('is_stale') else 'справочный'
            sentences.append(f"Условная валовая ценность электричества — {span(gross,'₸')} при {price.get('value'):g} ₸/кВт·ч ({r.region}, {stale} ориентир от {date}"+(f", возраст {age} дн." if age is not None else '')+"); это не чистая прибыль.")
        sentences.append('Чистая выгода и сравнение с продажей пока не определены: нужны предложение покупателя, энергопотребление, подготовка, обслуживание, хранение и доставка; неизвестные затраты не приняты за ноль.')
    studies=out.get('conditions',{}).get('studies',[])
    if 'temperature' in goals:
        temps=sorted({s['temperature_c'] for s in studies if s.get('temperature_c') is not None})
        sentences.append(f"В сопоставимых лабораторных опытах использовали {' / '.join(str(t) for t in temps)} °C; это ориентир для проверки с вашим инокулюмом и типом процесса, а не найденный оптимум." if temps else 'Для этого состава подходящая температура пока не подтверждена; нужны тип процесса и адаптация инокулюма.')
    if 'duration' in goals:
        days=sorted({s['duration_days'] for s in studies if s.get('duration_days')})
        sentences.append(f"Лабораторные испытания длились {' / '.join(str(t) for t in days)} дней; срок вашей партии зависит от загрузки и инокулюма и пока не рассчитан." if days else 'Срок партии пока неизвестен: нет подходящих данных о скорости разложения и инокулюме.')
    if r.reactor_total_volume_l and (mix or studies):
        volume=mix.get('sum_separate_volumes_l')
        if volume and volume['low']>=r.reactor_total_volume_l:sentences.append(f"Объём сырья уже не меньше полного объёма реактора {r.reactor_total_volume_l:g} л: для инокулюма и газового пространства места нет; такую разовую загрузку не предлагаю.")
        else:sentences.append(f"Реактор {r.reactor_total_volume_l:g} л: рабочий объём, инокулюм и свободное пространство нужно проверить отдельно; полное заполнение не разрешено.")
    if detail and mix:
        sentences.append('Расчёт: масса = объём × плотность; VS = масса × доля VS; метан, м³ = VS, кг × BMP, мл/г ÷ 1000; диапазоны сценария не имеют проверенного вероятностного покрытия.')
    return sentences or ['Состав сохранён; могу оценить газ, условия процесса или экономику.']

def reply(agent,state,text,sentences,trace,started,pending=None,updated=True,outputs=None,proposal=None):
    body=' '.join(sentences);sources=list({s['id']:s for result in (outputs or {}).values() for s in result.get('sources',[])}.values())
    if outputs and outputs.get('economics'):
        a=outputs['economics']['decision_analysis'];sources+=a.get('references',[])
        for role,price in a.get('prices',{}).items():
            if isinstance(price.get('source'),str) and price['source'].startswith('https://'):sources.append({'id':'price-'+role,'url':price['source'],'title':f"{role}: {price.get('value')} {price.get('unit')} · {price['status']}"})
    for study in (outputs or {}).get('conditions',{}).get('studies',[]):sources.append(study['source'])
    sources=list({s.get('url'):s for s in sources if s.get('url')}.values())
    public=state.model_dump(mode='json');public['advanced']={k:v for k,v in public.get('advanced',{}).items() if k not in {'cache','last_results'}};public['smart_cache']={}
    result_outputs=outputs or {}
    research_result=(result_outputs.get('gas',{}).get('mixture') or result_outputs.get('conditional_slurry_reference',{}).get('mixture'))
    if research_result:
        research_result=copy.deepcopy(research_result)
        components=research_result.get('components',[])
        if len(components)==1:
            research_result['mixture_result_level']=research_result.get('result_level')
            research_result['result_level']=components[0].get('result_level',research_result.get('result_level'))
    return {'conversation_version':'7','smart_agent_version':'8.0','advanced_conversation_version':'8.0','mode':'llm_tools' if proposal else 'deterministic_tools_no_llm','answer':body,'user_facing_answer':{'paragraphs':[body],'question':pending.model_dump() if pending else None,'sources':sources,'modes':['conditional_reference'],'assumptions':[]},'tools':trace,'provider_status':list(agent.llm.status),'pending_question':pending.model_dump() if pending else None,'context':agent.context,'context_updated':updated,'memory':public,'missing':pending.fields if pending else [],'actuator_access':False,'policy_tool_plan':[t['tool'] for t in trace],'technical_metadata':{'smart_version':'8.0','advanced_version':'8.0','tool_calls':trace,'pending_task':state.advanced.get('task'),'normalized_components':state.advanced.get('scenario',state.advanced.get('inventory',[])),'results':result_outputs,'research_result':research_result,'llm_proposal':proposal.model_dump() if proposal else None,'latency_seconds':time.perf_counter()-started,'uncertainty_status':'Sensitivity scenario only; no verified probability coverage','validation_errors':[]}}
