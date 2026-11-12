"""v5.6 conversational boundary; legacy Agent/ToolRegistry remain compatible."""
import json
import re
import time
import os
from src.agent import nlu
from src.agent.clarifications import question
from src.agent.dialogue_memory import apply,from_context,tool_context,fact
from src.agent.dialogue_response import answer,choose
from src.agent.dialogue_types import DialogueState,Extraction
from src.agent.dialogue_tools import DialogueTools,initial_plan,methane_ready,market_compare_ready
from src.agent.providers import HybridLLM
from src.agent.tools import ToolRegistry,get_model_info
from src.economics.calculator import ECONOMIC_FIELDS
from src.agent import process_bridge


def _correct_volume_mass_label(text, state):
    if not isinstance(text,str) or state.value('unit') not in {'L','m3'} or state.value('mass_kg') is not None:
        return text
    quantity=state.value('quantity')
    if quantity is None:return text
    amount=format(float(quantity),'.12g')
    amount_pattern=re.escape(amount)
    if '.' in amount:amount_pattern+='|'+re.escape(amount.replace('.',','))
    unit_pattern=r'(?:\u043b(?:\u0438\u0442\u0440\w*)?|l(?:iters?|itres?)?)'
    labels=(r'(?:wet\s+)?mass(?:\s+of)?',
            r'(?:(?:\u0432\u043b\u0430\u0436\u043d\w*|\u043e\u0446\u0435\u043d\u043e\u0447\u043d\w*)\s+)?'
            r'(?:\u043c\u0430\u0441\u0441\u0430|\u043c\u0430\u0441\u0441\u0443|\u043c\u0430\u0441\u0441\u044b)'
            r'(?:\s+(?:\u0441\u044b\u0440\u044c\u044f|\u043f\u0430\u0440\u0442\u0438\u0438|\u043d\u0430\u0432\u043e\u0437\u0430))?')
    pattern=re.compile(rf'(?P<label>{labels[0]}|{labels[1]})\s*(?:(?:is|=|:|'
                        r'\u0441\u043e\u0441\u0442\u0430\u0432\u043b\u044f\u0435\u0442|'
                        r'\u0440\u0430\u0432\u043d\u0430)\s*)?'
                        rf'(?P<value>{amount_pattern})\s*(?P<unit>{unit_pattern})',re.I)
    label='feedstock volume' if state.language=='en' else 'шикізат көлемі' if state.language=='kk' else 'объём сырья'
    return pattern.sub(lambda m:f"{label} {m.group('value')} {m.group('unit')}",text)


def _attach_capacity_notice(reply, assessment, language, state):
    from src.optimizer.capacity import render_capacity_notice
    notice = render_capacity_notice(assessment or {}, language)
    facing = reply.get('user_facing_answer')
    if not isinstance(facing, dict):
        facing = {}
        reply['user_facing_answer'] = facing
    paragraphs = facing.get('paragraphs')
    if not isinstance(paragraphs, list):
        paragraphs = []
        facing['paragraphs'] = paragraphs
    paragraphs[:]=[_correct_volume_mass_label(paragraph,state) for paragraph in paragraphs]
    sections=facing.get('sections')
    if isinstance(sections,list):
        for section in sections:
            if isinstance(section,dict) and isinstance(section.get('body'),str):
                section['body']=_correct_volume_mass_label(section['body'],state)
    if isinstance(reply.get('answer'),str):
        reply['answer']=_correct_volume_mass_label(reply['answer'],state)
    if not notice:
        return
    paragraphs[:] = [paragraph for paragraph in paragraphs if paragraph != notice]
    paragraphs.insert(0, notice)
    current = reply.get('answer', '')
    if not current.startswith(notice):
        current=current.replace(notice,'',1).strip()
        reply['answer'] = notice + ('\n\n' + current if current else '')
    if isinstance(sections,list) and sections:
        first=sections[0]
        if isinstance(first,dict) and isinstance(first.get('body'),str) and not first['body'].startswith(notice):
            body=first['body'].replace(notice,'',1).strip()
            first['body']=notice+('\n\n'+body if body else '')
    reply.setdefault('technical_metadata', {})['reactor_capacity_assessment'] = assessment


class ConversationAgent:
    def __init__(self,mode='auto',context=None,llm=None,registry=None,state=None,conversation_id=None,research_enabled=False):
        self.state=DialogueState.model_validate(state) if state else from_context(context,conversation_id)
        self.llm=llm or HybridLLM(mode,strict_model=research_enabled or self.state.version=='7');self.registry=registry or ToolRegistry()
        self.context=tool_context(self.state);self.history=[];self.last_pending=[]
        self.research_enabled=research_enabled or self.state.version=='7'
        if self.research_enabled:self.state.version='7'

    def reset(self):
        preferred={'model':self.context['model']} if 'model' in self.context else {}
        self.state=from_context(preferred,self.state.conversation_id);self.context=tool_context(self.state)
        if self.research_enabled:self.state.version='7'
        self.history=[];self.last_pending=[]

    def emit_progress(self,stage,details=None):
        callback=getattr(self,'progress',None)
        if callback:callback(stage,details)

    def ask(self,text):
        from src.agent import task_state
        prior=self.state.model_copy(deep=True);history=list(self.history)
        self._request_events=[task_state.event('RequestReceived','conversation_api',characters=len(text) if isinstance(text,str) else None)]
        self._prepared_extraction=None;self._input_issues=[];self._capacity_assessment=None
        try:
            extraction=nlu.extract(text,self.state)
            self._request_events.append(task_state.event('ParametersExtracted','parameter_extraction',entities=[e.model_dump(mode='json') for e in extraction.entities]))
            prepared,events,self._input_issues=task_state.prepare(text,self.state,extraction)
            self._request_events.extend(events+self._input_issues)
            self._prepared_extraction=extraction
            self.state=prepared
            if not self._input_issues:
                from src.optimizer.capacity import assess_dialogue_state
                capacity_state=apply(prepared,extraction,tolerate_engineering_conflicts=self.research_enabled)
                self._capacity_assessment=assess_dialogue_state(capacity_state)
                if self._capacity_assessment.get('status') not in {'NOT_ASSESSED','INVALID_INPUT'}:
                    self._request_events.append(task_state.event(
                        'ReactorCapacityChecked','physical_constraint_preflight',
                        assessment=self._capacity_assessment.copy()))
            if any(e['type']=='NewBatch' for e in events):self.history=[]
            self.context=tool_context(self.state)
            preview=self.state.model_dump(mode='json')
            for entity in extraction.entities:
                if entity.provenance=='USER_CONFIRMED':preview['facts'][entity.name]=fact(entity.value,entity.unit,entity.provenance,entity.evidence).model_dump(mode='json')
            self.emit_progress('parameters',{'preview':preview})
        except (ValueError,TypeError) as exc:
            issue=task_state.event(task_state.EventType.InvalidPhysicalParameters,'parameter_extraction',reason=str(exc))
            self._request_events.append(issue)
            reply=task_state.rejected(self,[issue])
        else:
            reply=self._ask(text)
        if reply.get('context_updated') is False:
            self.state=prior;self.context=tool_context(prior);self.history=history
        if self._capacity_assessment:
            _attach_capacity_notice(reply,self._capacity_assessment,self.state.language,self.state)
        metadata=reply.setdefault('technical_metadata',{})
        for trace in reply.get('tools',[]):
            self._request_events.append(task_state.event('ToolExecuted','tool_execution',tool=trace['tool'],status=trace['status']))
            missing=trace.get('result',{}).get('missing',[])
            if missing:self._request_events.append(task_state.event(task_state.EventType.MissingScientificParameters,'tool_execution',tool=trace['tool'],fields=missing))
        self._request_events.append(task_state.event('ResponseCreated','response',mode=reply.get('mode'),tool_count=len(reply.get('tools',[]))))
        metadata['diagnostic_events']=self._request_events
        return reply

    def _ask(self,text):
        advanced_match=False
        if self.research_enabled:
            from src.agent import advanced_conversation
            advanced_match=advanced_conversation.applicable(text,self.state)
            configured=any(getattr(provider,'configured',False) for provider in getattr(self.llm,'providers',[]))
            if advanced_match and not configured and not self._input_issues and not getattr(self,'deterministic_research_fallback',False):
                try:return advanced_conversation.respond(self,text)
                except (ValueError,TypeError,OSError):
                    return advanced_conversation.reply(self,self.state,text,['Не удалось проверить расчёт по этим данным; предыдущая партия сохранена. Уточните единицы и свойства сырья.'],[],time.perf_counter(),updated=False)
        original_state=self.state.model_copy(deep=True)
        started=time.perf_counter();validation_errors=[];grounding_rejections=[];advisor_plan=None
        try:extraction=self._prepared_extraction or nlu.extract(text,self.state)
        except (ValueError,TypeError) as exc:
            message=choose(self.state.language,'Не удалось принять эти данные. Проверьте число, единицы и соответствие измерений.','I could not accept those inputs. Please check the number, units and consistency.','Бұл деректер қабылданбады. Санын, бірліктерін және өлшемдердің сәйкестігін тексеріңіз.')
            return {'conversation_version':'7' if self.research_enabled else '5.6','mode':'input_rejected','answer':message,'user_facing_answer':{'paragraphs':[message],'question':None,'sources':[],'modes':['validation'],'assumptions':[]},
                'tools':[],'context_updated':False,'provider_status':[],'missing':[],'context':dict(self.context),'actuator_access':False,
                'technical_metadata':{'validation_errors':[str(exc)],'uncertainty_status':'not_quantified','fallback_reason':None}}
        from src.agent.smart_intent import identify,fast_followup
        smart_plan=identify(text,self.state) if self.research_enabled else None
        fast=bool(smart_plan and fast_followup(text,self.state,smart_plan))
        if fast and any(getattr(provider,'configured',False) for provider in getattr(self.llm,'providers',[])):fast=False
        entity_names={entity.name for entity in extraction.entities}
        simple_quantity_correction=(self.research_enabled and getattr(self,'runtime_version',None)=='9'
            and extraction.correction and not extraction.new_batch and self.state.value('quantity') is not None
            and 'quantity' in entity_names and entity_names <= {'quantity','unit'}
            and bool(re.search(r'исправлени|поправ|вместо|correction|instead|түзету',text,re.I))
            and not re.search(r'рассчита|пересчита|выход|метан|биогаз|выгод|температур|calculate|recalculat|yield|methane|biogas',text,re.I))
        simple_batch_capture=(self.research_enabled and getattr(self,'runtime_version',None)=='9' and extraction.new_batch
            and {'quantity','material'} <= entity_names
            and entity_names <= {'quantity','unit','material','physical_state','material_state'}
            and bool(re.search(r'запомни|сохрани|зафиксируй|remember|record|сақта',text,re.I))
            and not re.search(r'рассчита|пересчита|выход|метан|биогаз|выгод|температур|calculate|recalculat|yield|methane|biogas',text,re.I))
        if fast:self.llm.status=[]
        timeouts=[]
        if self.research_enabled:
            remaining=max(.1,started+max(1,min(600,float(os.getenv('BIOREACTOR_AGENT_TIMEOUT','120'))))-time.perf_counter())
            for provider in getattr(self.llm,'providers',[]):
                if hasattr(provider,'timeout'):
                    timeouts.append((provider,provider.timeout));provider.timeout=min(provider.timeout,remaining)
        from src.agent.task_state import event
        self._request_events.append(event('ModelUnderstandingStarted','model_understanding',configured=any(getattr(p,'configured',False) for p in getattr(self.llm,'providers',[]))))
        self.emit_progress('understanding')
        understanding=self.state.brief()
        if self._capacity_assessment and self._capacity_assessment.get('status') not in {'NOT_ASSESSED','INVALID_INPUT'}:
            if isinstance(understanding,dict):
                understanding=dict(understanding)
                understanding['reactor_capacity_preflight']=self._capacity_assessment
            else:
                understanding+='\nDeterministic reactor capacity preflight (binding; never infer working volume from nominal): '+json.dumps(self._capacity_assessment,ensure_ascii=False)
        try:proposal=self.llm.interpret(text,understanding) if hasattr(self.llm,'interpret') and not fast and not simple_quantity_correction else None
        finally:
            for provider,previous in timeouts:provider.timeout=previous
        self._request_events.append(event('ModelUnderstandingFinished','model_understanding',proposal_received=proposal is not None,providers=list(self.llm.status)))
        if self._input_issues:
            from src.agent.task_state import rejected
            return rejected(self,self._input_issues,extraction)
        if proposal:
            extraction=nlu.augment_requested_tasks(extraction,proposal,text)
            if smart_plan is not None and not smart_plan['goals'] and not smart_plan.get('definition') and not smart_plan['edit'] and re.search(r'\?|как|подскажи|посовет|how|what|қалай|қандай',text,re.I):
                mapping={'methane_yield':['gas'],'temperature_recommendation':['temperature'],'economic_comparison':['economics'],'reactor_status':['reactor'],'process_guidance':['temperature','duration']}
                smart_plan['goals']=list(dict.fromkeys(goal for intent in proposal.intents for goal in mapping.get(intent,[])))
                if smart_plan['goals']:smart_plan['intent_origin']='local_llm_proposal_restricted_to_allowed_goals'
            # Model output is a proposal. Every new fact must be anchored in a
            # literal span and pass the independent unit/material grammar.
            candidates=[(p.name,p.text) for p in proposal.entities]
            if proposal.material and proposal.material_evidence:candidates.append(('material',proposal.material_evidence))
            names={e.name for e in extraction.entities}
            for name,span in candidates:
                if span.casefold() not in text.casefold():grounding_rejections.append({'name':name,'reason':'evidence_not_in_message'});continue
                try:verified=nlu.extract(span,self.state)
                except ValueError:grounding_rejections.append({'name':name,'reason':'invalid_evidence_units'});continue
                matches=[e for e in verified.entities if e.name==name]
                if name=='material':matches=[e for e in matches if e.value==proposal.material]
                if not matches:grounding_rejections.append({'name':name,'reason':'not_supported_by_independent_grammar'});continue
                if name not in names:
                    extraction.entities.append(matches[-1]);names.add(name)
            if not extraction.intents and not self.state.intents and re.search(r'\?|\bкак\b|\bчто\b|почему|можно|\bhow\b|\bwhat\b|\bwhy\b|\bcan\b|қандай|қалай|қанша',text,re.I):extraction.intents=list(proposal.intents)
        try:
            if self.research_enabled:
                from src.agent import research_bridge
                extraction=research_bridge.augment(text,self.state,extraction)
                from src.agent import advisor_bridge
                extraction,advisor_plan=advisor_bridge.prepare(text,self.state,extraction)
            if not (advisor_plan or self.research_enabled and (self.state.mixture_components or self.state.mixture_scenario_components)):extraction=process_bridge.augment(text,self.state,extraction)
            if self.research_enabled and re.search(r'если|what\s+if',text,re.I):
                for entity in extraction.entities:
                    if entity.name=='dilution_water_l':entity.provenance='ASSUMED_FOR_SCENARIO'
            next_state=apply(self.state,extraction,tolerate_engineering_conflicts=self.research_enabled)
            if self.research_enabled:
                from src.agent import decision_bridge
                species_changed=next_state.value('material')!=self.state.value('material') and self.state.value('material') not in {None,'manure'}
                next_state.decision_settings=decision_bridge.propose(text,self.state,extraction.new_batch or species_changed)
                quantity_changed=(next_state.value('quantity'),next_state.value('unit'))!=(self.state.value('quantity'),self.state.value('unit'))
                if quantity_changed and self.state.value('quantity') is not None:
                    explicit=json.loads(text).get('decision_inputs',{}).get('reactor',{}) if text.lstrip().startswith('{') else {}
                    for key in ['heated_mass_kg','auxiliary_energy_kwh','loads','loads_complete','energy_scope']:
                        if key not in explicit:next_state.decision_settings.get('reactor',{}).pop(key,None)
                from src.economics.decision_schemas import ReactorInputs
                for entity in extraction.entities:
                    if entity.name in ReactorInputs.model_fields and entity.provenance=='USER_CONFIRMED':next_state.decision_settings.setdefault('reactor',{})[entity.name]=entity.value
                    aliases={'recovery_fraction':'recovery_fraction','methane_fraction':'methane_fraction','electricity_efficiency':'electrical_efficiency'}
                    if entity.name in aliases and entity.provenance=='USER_CONFIRMED':next_state.decision_settings[aliases[entity.name]]={'low':entity.value,'high':entity.value,'provenance':'USER_REPORTED','evidence':entity.evidence}
            if re.fullmatch(r'\s*(?:не знаю|неизвестно|нет данных|unknown|i don.t know|білмеймін|белгісіз)[.!]?\s*',text,re.I) and self.state.pending_question:
                for name in self.state.pending_question.fields:next_state.facts[name]=fact(None,provenance='UNKNOWN',evidence=text)
                if self.research_enabled:next_state.decision_unavailable=list(set(next_state.decision_unavailable+self.state.pending_question.fields))
            if not next_state.intents:
                next_state.intents=['methane_yield'] if any(e.name in {'bmp_ml_ch4_g_vs','c_vs_sub_m','ISR'} for e in extraction.entities) else ['general']
            if self.research_enabled:next_state=advisor_bridge.commit(next_state,self.state,advisor_plan,text,extraction)
            context=tool_context(next_state)
        except (ValueError,TypeError) as exc:
            from src.agent.task_state import rejected,EventType,event
            kind=EventType.AmbiguousIntent if 'Unbound material' in str(exc) or 'Specify' in str(exc) or 'Ambiguous' in str(exc) else EventType.InvalidPhysicalParameters
            issue=event(kind,'state_validation',reason=str(exc))
            self._request_events.append(issue)
            reply=rejected(self,[issue],extraction)
            reply['technical_metadata'].update(validation_errors=[str(exc)],grounding_rejections=grounding_rejections)
            return reply
        self.state=next_state;self.context=context
        self.emit_progress('planning',{'preview':self.state.model_dump(mode='json')})
        if self.research_enabled:
            if simple_batch_capture:
                from src.agent.batch_intent import confirmation
                message=confirmation(self.state)
                if message:
                    self.history=(self.history+[text])[-8:]
                    return {'conversation_version':'7','analysis_version':'9.0','mode':'deterministic_batch_confirmation',
                        'answer':message,'user_facing_answer':{'paragraphs':[message],'sections':[],'question':None,'sources':[],
                        'modes':['deterministic_batch_confirmation'],'assumptions':[]},'tools':[],'provider_status':list(self.llm.status),
                        'memory':self.state.model_dump(mode='json'),'context':dict(self.context),'context_updated':True,
                        'pending_question':None,'missing':[],'actuator_access':False,
                        'technical_metadata':{'final_author':'confirmed_state','verification':{'status':'not_applicable','checked':False},
                        'scientific_answer_verification':{'status':'not_applicable','checked':False},
                        'quantity_verification':{'status':'passed','checked':True,'scope':'Direct display of confirmed batch state.'},
                        'diagnostics':[{'stage':'deterministic_batch_confirmation','reason':'explicit_state_capture'}]}}
            if simple_quantity_correction:
                quantity=self.state.value('quantity');unit=self.state.value('unit')
                unit_label={'L':'л','m3':'м³','kg':'кг','g':'г','t':'т'}.get(unit,unit or '')
                amount=format(float(quantity),'.12g').replace('.',',')
                label='текущий объём сырья' if unit in {'L','m3'} else 'текущая масса сырья'
                message=choose(self.state.language,f'Исправление сохранено: {label} — {amount} {unit_label}.',
                    f'Correction saved: the current feedstock quantity is {amount} {unit or ""}.',
                    f'Түзету сақталды: ағымдағы шикізат мөлшері — {amount} {unit_label}.')
                self.history=(self.history+[text])[-8:]
                return {'conversation_version':'7','analysis_version':'9.0','mode':'deterministic_parameter_correction',
                    'answer':message,'user_facing_answer':{'paragraphs':[message],'sections':[],'question':None,'sources':[],
                    'modes':['deterministic_parameter_correction'],'assumptions':[]},'tools':[],'provider_status':[],
                    'memory':self.state.model_dump(mode='json'),'context':dict(self.context),'context_updated':True,
                    'pending_question':None,'missing':[],'actuator_access':False,
                    'technical_metadata':{'final_author':'confirmed_state','verification':{'status':'not_applicable','checked':False},
                    'scientific_answer_verification':{'status':'not_applicable','checked':False},
                    'quantity_verification':{'status':'passed','checked':True,'scope':'Direct display of the confirmed quantity; no calculation.'},
                    'diagnostics':[{'stage':'deterministic_correction','reason':'unambiguous_confirmed_quantity'}]}}
            if proposal is None and getattr(self,'deterministic_research_fallback',False) and getattr(self,'runtime_version',None)=='9':
                # The experimental UI must retain the same checked Python
                # evidence path when its resource gate withholds the model.
                from src.agent import runtime9
                return runtime9.run(self,text,extraction,proposal,started)
            if proposal is None and any(getattr(p,'configured',False) for p in getattr(self.llm,'providers',[])):
                from src.agent.autonomous import provider_failure
                return provider_failure(self,text,extraction,started)
            if advanced_match and proposal is None:
                # Preserve the established no-LLM v8.1 task graph when local
                # generation is unavailable or returns an invalid proposal.
                self.state=original_state;self.context=tool_context(self.state)
                try:return advanced_conversation.respond(self,text)
                except (ValueError,TypeError,OSError):
                    return advanced_conversation.reply(self,self.state,text,['Verified analysis was unavailable for these inputs; prior batch data were retained. Please confirm the units and substrate properties.'],[],started,updated=False)
            if proposal is not None and getattr(self.llm,'active',None) is not None:
                self._request_events.append(event('PlanningStarted','agent_planning',task_id=self.state.task_id))
                if getattr(self,'runtime_version',None)=='9':
                    from src.agent import runtime9
                    return runtime9.run(self,text,extraction,proposal,started)
                from src.agent import autonomous
                return autonomous.run(self,text,extraction,proposal,started)
            from src.agent import smart_bridge
            if smart_bridge.applicable(self.state,smart_plan,text):return smart_bridge.respond(self,text,extraction,proposal,started,smart_plan,advisor_plan)
            from src.agent import advisor_bridge
            if advisor_bridge.applicable(self.state,text):return advisor_bridge.respond(self,text,extraction,proposal,started,advisor_plan)
            from src.agent import research_bridge
            if research_bridge.applicable(self.state,text):return research_bridge.respond(self,text,extraction,proposal,started)
        registry=DialogueTools(self.registry,self.state,text);results={};trace=[]
        def execute(name,execution_context=None):
            result=registry.execute(name,execution_context or context,results,text)
            try:
                json.dumps(result,allow_nan=False)
                if not isinstance(result,dict) or not isinstance(result.get('message'),str) or 'status' not in result:raise ValueError('Invalid tool protocol')
            except (ValueError,TypeError):result={'status':'error','message':'Tool result rejected by protocol validation'}
            origin='validated_process_inputs_with_separate_assumptions' if name in process_bridge.PROCESS_TOOLS else 'explicit_scenario_assumptions' if execution_context else 'grounded_user_facts_and_verified_tool_results'
            results[name]=result;trace.append({'tool':name,'status':result['status'],'input_origin':origin,'result':result})
        process_plan=process_bridge.plan(self.state,text)
        base_plan=[] if process_plan==['estimate_process_energy'] else initial_plan(self.state,context,text)
        for name in base_plan:execute(name)
        intents=set(self.state.intents)
        if results.get('predict_bmp',{}).get('status')=='unsupported' and 'search_scientific_sources' not in results:execute('search_scientific_sources')
        if 'economic_comparison' in intents and context.get('potential_methane_m3') is None and context.get('bmp_ml_ch4_g_vs') is None and 'predict_bmp' not in results:
            required=['c_vs_sub_m','c_vs_sub_f','c_vs_inoc','ISR','vs_mass_kg']
            if context.get('material') in get_model_info(context.get('model','stage1_5'))['supported_substrates'] and all(context.get(k) is not None for k in required):execute('predict_bmp')
        if 'methane_yield' in intents and methane_ready(context,results):execute('calculate_methane')
        if 'economic_comparison' in intents and results.get('predict_bmp',{}).get('status')=='ok' and methane_ready(context,results) and 'calculate_methane' not in results:execute('calculate_methane')
        if 'economic_comparison' in intents:
            scenario=dict(context)
            from src.agent.context import NUMBERS,TEXT,validate_context
            for key,entry in self.state.assumptions.items():
                if key in NUMBERS|TEXT:scenario[key]=entry.value
            quantity=self.state.assumptions.get('quantity');unit=self.state.assumptions.get('unit')
            if quantity and unit and unit.value in {'kg','t','g'}:scenario['mass_kg']=quantity.value*{'kg':1,'t':1000,'g':.001}[unit.value]
            try:scenario=validate_context(scenario)
            except ValueError:scenario=context
            if all(scenario.get(key) is not None for key in ECONOMIC_FIELDS):execute('calculate_profitability',scenario if scenario!=context else None)
            else:
                store=self.registry.market_store
                if store is None:
                    from src.market.service import get_store
                    store=get_store()
                if market_compare_ready(store,context,results):execute('compare_market_scenarios')
        for name in process_plan:
            execute(name,{'process_request':process_bridge.request_data(self.state)})
        prediction=results.get('predict_bmp',{})
        if prediction.get('status')=='ok':
            self.state.estimates['bmp_ml_ch4_g_vs']=fact(prediction['bmp'],'mL CH4/g VS','MODEL_ESTIMATED',prediction['model_version'],['material','c_vs_sub_m','c_vs_sub_f','c_vs_inoc','ISR'])
        for claim in results.get('recommend_conditions',{}).get('claims',[]):
            self.state.source_verified[claim['id']]=fact({'values':claim['values'],'unit':claim['unit'],'scope':claim['scope'],'source_id':claim['source_id']},provenance='SOURCE_VERIFIED',evidence=claim['id'])
        pending=process_bridge.pending(self.state,results,question(self.state,context,results));self.state.pending_question=pending
        missing=list(dict.fromkeys([key for result in results.values() for key in result.get('missing',[])] + (pending.fields if pending else [])))
        body,facing=answer(self.state,results,extraction,pending,proposal is not None)
        self.history=(self.history+[text])[-8:];self.last_pending=[name for name,r in results.items() if r['status']=='needs_input']
        if any(key!='market_region' for key in self.state.assumptions):
            for name in ['compare_market_scenarios','calculate_profitability']:
                if name in results:results[name]['final_recommendation']=None;results[name]['is_final_recommendation']=False;results[name]['scenario_assumptions_present']=True
        mode='llm_tools' if proposal is not None else 'deterministic_tools_no_llm'
        metadata={'tool_calls':trace,'model_versions':{name:r.get('model_version',r.get('version')) for name,r in results.items() if r.get('model_version') or r.get('version')},
            'data_provenance':{key:value.model_dump() for key,value in {**self.state.facts,**self.state.derived}.items()},
            'confirmed_parameters':{k:f.model_dump() for k,f in self.state.facts.items() if f.provenance=='USER_CONFIRMED'},
            'assumptions':{k:f.model_dump() for k,f in self.state.assumptions.items()},'derived_parameters':{k:f.model_dump() for k,f in self.state.derived.items()},
            'source_verified':{k:f.model_dump() for k,f in self.state.source_verified.items()},'model_estimated':{k:f.model_dump() for k,f in self.state.estimates.items()},
            'missing_parameters':missing,'validation_errors':validation_errors,'uncertainty_status':'not_quantified; no validated finite 90% interval',
            'fallback_reason':None if proposal is not None else 'no_available_valid_structured_llm; deterministic_nlu_and_grounded_responses',
            'grounding_rejections':grounding_rejections,'extracted_entities':extraction.model_dump(),'llm_proposal':proposal.model_dump() if proposal else None,
            'invalidated_parameters':self.state.invalidated,'deferred_tools':[name for intent,name in [('methane_yield','calculate_methane'),('economic_comparison','compare_market_scenarios')] if intent in intents and name not in results],
            'latency_seconds':time.perf_counter()-started,'optimizer_version':'6' if self.state.value('process_optimizer_active') else None}
        return {'conversation_version':'7' if self.research_enabled else '5.6','mode':mode,'answer':body,'user_facing_answer':facing,'technical_metadata':metadata,
            'tools':trace,'provider_status':list(self.llm.status),'missing':missing,'context':dict(context),
            'pending_question':pending.model_dump() if pending else None,'memory':self.state.model_dump(mode='json'),
            'context_updated':True,'actuator_access':False,'policy_tool_plan':[r['tool'] for r in trace]}
