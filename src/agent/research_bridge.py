"""v7 opt-in: literature is never written to confirmed batch measurements."""
import os,re,time
from src.agent.dialogue_types import Entity,Question
from src.estimation.schemas import EstimateRequest
RESEARCH_TOOLS=['research_scientific_evidence','research_market_offers','estimate_from_literature','research_and_estimate']
STATES={'compost':r'компост|перегно|\bcompost','bedded':r'подстил|\bbedded\b',
        'slurry':r'навозн\w*\s+жиж|жидк\w*\s+навоз|суспенз|\bslurry\b|сұйық\s+көң',
        'dry':r'сух\w*\s+навоз|высуш|\bdry\b','fresh_solid':r'твёрд\w*\s+навоз|тверд\w*\s+навоз|\bsolid\b'}
def augment(text,state,extraction):
    if state.value('material') in {'cattle_manure','swine_manure','poultry_manure'} and not extraction.new_batch and not re.search(r'неизвест|не знаю|не коров|не свин|не птич',text,re.I):
        extraction.entities=[e for e in extraction.entities if not (e.name=='material' and e.value=='manure')]
    candidates=[];negated=[]
    for name,pattern in STATES.items():
        match=re.search(pattern,text,re.I)
        if match:
            if re.search(r'(?:\bне|\bnot)\s+$',text[:match.start()],re.I):negated.append(name)
            else:candidates.append((name,match))
    if any(name=='bedded' for name,_ in candidates):candidates=[(name,m) for name,m in candidates if name!='fresh_solid']
    uncertain=bool(re.search(r'не знаю|не уверен|неизвест|not sure|unknown',text,re.I))
    hypothetical=bool(re.search(r'\bесли\b|допустим|предполож|\bif\b|assum',text,re.I))
    if len(candidates)==1 and not uncertain and not hypothetical:
        name,match=candidates[0];extraction.entities.append(Entity(name='material_state',value=name,evidence=match.group()))
        from src.advisor.material_axes import extract as material_axes
        physical=material_axes(match.group()).get('physical_state')
        if physical and not any(e.name=='physical_state' for e in extraction.entities):
            extraction.entities.append(Entity(name='physical_state',value=physical,evidence=match.group()))
    elif not hypothetical and (len(candidates)>1 or candidates and uncertain or state.value('material_state') in negated):
        extraction.entities.append(Entity(name='material_state',value='unknown',provenance='UNKNOWN',evidence=text))
    return extraction
def applicable(state,text):
    if state.value('material') not in {'cattle_manure','swine_manure','poultry_manure','food_waste'}:return False
    if state.value('material_volume_l') is None and state.value('mass_kg') is None:return False
    if state.decision_settings.get('gas_use','unknown')!='unknown' and not set(state.intents)&{'reactor_status','model_info','price_history'}:return True
    if state.last_research_summary and state.pending_question and state.pending_question.id.startswith('decision-'):return True
    if set(state.intents)&{'temperature_recommendation','reactor_status','model_info','price_history'} and not set(state.intents)&{'economic_comparison','methane_yield'}:return False
    return bool(set(state.intents)&{'economic_comparison','methane_yield','market_prices','sources','process_guidance'} or state.pending_question and state.pending_question.id=='research-material-form')
def request_data(state):
    data={'material':state.value('material'),'material_state':state.value('material_state','unknown'),
          'region':state.value('market_region') or 'KZ-Karaganda','region_confirmed':state.value('market_region') is not None,'online':os.getenv('BIOREACTOR_RESEARCH_ONLINE','1')=='1'}
    fields={'volume_l':'material_volume_l','mass_kg':'mass_kg','density_kg_l':'density_kg_l','vs_mass_kg':'vs_mass_kg','bmp_ml_g_vs':'bmp_ml_ch4_g_vs','gas_reference':'gas_volume_basis','methane_fraction':'methane_fraction','reactor_total_volume_l':'reactor_total_volume_l'}
    for dst,src in fields.items():
        if state.value(src) is not None:data[dst]=state.value(src)
    if state.value('ts_percent') is not None:data['ts_fraction']=state.value('ts_percent')/100
    if state.value('vs_percent') is not None and state.value('vs_basis') in {'TS','fresh_mass'}:data['vs_fraction_of_ts' if state.value('vs_basis')=='TS' else 'vs_fraction_wet']=state.value('vs_percent')/100
    from src.economics.calculator import ECONOMIC_FIELDS
    economics={k:state.value(k) for k in ECONOMIC_FIELDS if state.value(k) is not None}
    if economics:data['economic_inputs']=economics
    from src.economics.decision_schemas import ReactorInputs
    import copy
    preferences=copy.deepcopy(state.decision_settings)
    for target,source in [('recovery_fraction','recovery_fraction'),('methane_fraction','methane_fraction'),('electrical_efficiency','electricity_efficiency')]:
        if state.value(source) is not None and target not in preferences:preferences[target]={'low':state.value(source),'high':state.value(source),'provenance':'USER_REPORTED','evidence':'Explicit existing conversation parameter: '+source}
    for key in ReactorInputs.model_fields:
        if state.value(key) is not None and key not in preferences.get('reactor',{}):preferences.setdefault('reactor',{})[key]=state.value(key)
    data['decision']=preferences
    return data
def execute_tool(name,context,store):
    from src.research.orchestrator import research_and_estimate
    from src.research.evidence_store import EvidenceStore
    from src.research import scientific_search,market_search
    request=EstimateRequest.model_validate(context.get('research_request',context))
    if name in {'research_and_estimate','estimate_from_literature'}:
        if name=='estimate_from_literature':request=request.model_copy(update={'online':False})
        return {**research_and_estimate(store,request),'message':'Детерминированная оценка по проверенным источникам; факты партии не изменены.'}
    evidence=EvidenceStore(store)
    result=scientific_search.search(evidence,request.material,request.online) if name=='research_scientific_evidence' else market_search.search(evidence,request.material,request.region,request.online)
    return {**result,'status':'ok','message':'Поиск выполнен; метаданные новых публикаций не означают проверенные численные данные.'}
def respond(agent,text,extraction,proposal,started):
    from src.agent.decision_response import render
    from src.agent.decision_bridge import next_question
    state=agent.state;state.version='7';data=request_data(state)
    result=agent.registry.execute('research_and_estimate',{'research_request':data},{},text)
    trace=[{'tool':'research_and_estimate','status':result['status'],'input_origin':'confirmed_inputs_and_separate_reviewed_literature','result':result}]
    paragraphs=render(state,data,result)
    from src.agent.human_response import friendly,sections
    paragraphs=friendly(paragraphs,state.language)
    pending=next_question(state,data,result)
    state.pending_question=pending;agent.history=(agent.history+[text])[-8:];agent.last_pending=[]
    sources=[{'title':s['title'],'url':s['url']} for s in result.get('sources',[]) if s.get('url')]
    sources += [{'title':o['title'],'url':o['source_url']} for o in result.get('market',{}).get('offers',[])]
    facing={'paragraphs':paragraphs,'sections':sections(paragraphs,state.language),'question':pending.model_dump() if pending else None,'sources':sources,'modes':['literature_guidance',result.get('result_level') or 'research_incomplete'],'assumptions':result.get('assumptions',[])}
    return {'conversation_version':'7','analysis_version':'7.5','mode':'llm_tools' if proposal else 'deterministic_tools_no_llm','answer':'\n\n'.join(paragraphs),'user_facing_answer':facing,'tools':trace,'provider_status':list(agent.llm.status),'missing':result.get('missing',[]),'context':dict(agent.context),'context_updated':True,'memory':state.model_dump(mode='json'),'pending_question':pending.model_dump() if pending else None,'actuator_access':False,'policy_tool_plan':['research_and_estimate'],
            'technical_metadata':{'tool_calls':trace,'confirmed_parameters':{k:f.model_dump() for k,f in state.facts.items() if f.provenance=='USER_CONFIRMED'},'assumptions':result.get('assumptions',[]),'research_request':data,'extracted_entities':extraction.model_dump(),'llm_proposal':proposal.model_dump() if proposal else None,'research_result':result,'uncertainty_status':result.get('uncertainty_status'),'latency_seconds':time.perf_counter()-started,'fallback_reason':None if proposal else 'No structured local LLM; deterministic parser and research tools used'}}
