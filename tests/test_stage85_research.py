import pytest
from src.research.dossiers import CORE_MATERIALS, search, compare
from src.agent import analytical
from src.agent.scientific_tools import verify, execute
from src.agent.dialogue_types import DialogueState, Extraction
from src.agent.research_memory import finish_turn


def test_eight_dossiers_keep_paired_studies_and_historical_categories():
    result=search()
    assert len(result['dossiers'])==8
    assert all(d['studies'] and d['sources'] for d in result['dossiers'])
    assert all(s['provenance']=='PUBLISHED_EXPERIMENT' for d in result['dossiers'] for s in d['studies'])
    from src.advisor.catalog import get_catalog
    catalog=get_catalog()
    assert sum(m['scope_status']=='CORE' for m in catalog['materials'])==8
    assert any(m['id']=='dairy_waste' and m['scope_status']=='EXPERIMENTAL_RETAINED' for m in catalog['materials'])


def test_incompatible_studies_are_not_pooled():
    result=compare(['swine_manure'])
    assert len(result['studies'])>=2 and result['comparability_checks']
    assert result['pooled_bmp'] is None
    assert all(not c['pooling_allowed'] for c in result['comparability_checks'])


def test_source_check_never_claims_live_verification():
    result=execute('verify_scientific_sources',{'analytical_context':{'facts':{'material':'food_waste'},'components':[]}}, {}, '')
    assert result['sources']
    assert all(c['live_verification']=='NOT_PERFORMED' for c in result['checks'])


def test_independent_calculation_detects_corrupted_component():
    data={'facts':{'material':'food_waste','mass_kg':48},'components':[],'decision':{},'mode':'mixture','language':'ru'}
    results={'assess_substrate_potential':analytical.scientific(data)}
    assert verify(results)['all_checks_passed']
    results['assess_substrate_potential']['scenarios'][0]['components'][0]['methane_reference_m3']['low']+=1
    assert verify(results)['status']=='error'


def test_cost_categories_without_numbers_remain_unknown_and_do_not_repeat():
    state=DialogueState()
    facing={'paragraphs':[],'sections':[], 'question':{'id':'operating-costs','text':'Какие полные расходы?', 'fields':['operating_costs'],'options':[],'reason':''}}
    finish_turn(state,'Сколько выгоды?',Extraction(),dict(facing),'Какие полные расходы?',{})
    value,body,diagnostics=finish_turn(state,'Нагрев, обслуживание, подготовка',Extraction(),dict(facing),'Какие полные расходы?',{})
    assert state.decision_settings=={}
    assert state.advanced['research_dialogue']['unpriced_categories']==['heating','maintenance','preparation']
    assert value['question']['id']=='heating-kwh'
    assert 'не суммы' in body
    assert diagnostics[0]['reason']=='repeated_question_suppressed'
    assert body.count('?')==1


def test_dilution_requires_a_user_target_and_never_authorizes_operation():
    data={'facts':{'material':'food_waste','mass_kg':5},'components':[],'decision':{},'mode':'mixture','language':'ru'}
    science=analytical.scientific(data)
    result=execute('calculate_dilution_plan',{'analytical_context':data},{'assess_substrate_potential':science},'')
    assert result['missing']==['user_selected_target_ts_fraction']
    assert result['operation_authorized'] is False


def test_zero_water_is_a_valid_correction():
    from src.agent.nlu import extract
    result=extract('Вода не добавлена. dilution_water_l=0',DialogueState())
    assert next(e.value for e in result.entities if e.name=='dilution_water_l')==0


def test_nominal_capacity_gives_necessary_density_not_a_safe_density():
    data={'facts':{'material':'food_waste','mass_kg':48,'reactor_total_volume_l':90},'components':[],'decision':{},'mode':'mixture','language':'ru'}
    science=analytical.scientific(data)
    engineering=science['scenarios'][0]['engineering']
    assert engineering['necessary_mean_feed_density_kg_l']['low']==pytest.approx(48/90)
    assert engineering['operation_authorized'] is False
    assert engineering['status']=='REQUIRES_REVIEW'


def test_heating_answer_is_an_energy_input_without_claiming_complete_balance():
    from src.agent.decision_bridge import propose
    from src.agent.dialogue_types import Question
    state=DialogueState(pending_question=Question(id='heating-kwh',text='Сколько кВт·ч?',fields=['auxiliary_energy_kwh']))
    result=propose('2 кВт·ч',state)
    assert result['reactor']['auxiliary_energy_kwh']==2
    assert result['reactor'].get('energy_scope')!='entire_batch'


def test_unsupported_safety_and_profit_conclusions_are_rejected():
    from src.agent.autonomous import _unsupported_conclusions
    results={'assess_substrate_potential':{'scenarios':[{'engineering':{'status':'REQUIRES_REVIEW'},'result_level':'HYPOTHETICAL_SCENARIO'}]},
             'evaluate_partial_economics':{'profit_established':False}}
    assert _unsupported_conclusions('Можно безопасно загрузить. Чистая прибыль составит 100 тенге.',results)==['profit_without_complete_confirmed_economics','safety_without_validated_loading']


def test_local_model_final_with_unused_tool_field_is_not_executed():
    from src.agent.providers import JSONProvider
    provider=JSONProvider('offline',model='qwen3:8b')
    provider.generate=lambda *args,**kwargs:{'action':'final','tool':'get_model_info','arguments':{},'final':'Расчёт завершён.'}
    action=provider.autonomous_action('Вопрос',{}, {},[],[],['get_model_info'])
    assert action['action']=='final' and action['tool'] is None
    assert action['protocol_normalization']=='unused_tool_field_cleared_on_final'


@pytest.mark.parametrize('message',['Исправь: не 48 кг, а 5 кг пищевых отходов.', 'Not 48 kg but 5 kg food waste.'])
def test_rejected_old_mass_is_not_an_extra_mixture_component(message):
    from src.agent.mixture_parser import explicit_components
    components=explicit_components(message)
    assert len(components)==1 and components[0].quantity==5


def test_reported_conflicting_volumes_allow_partial_science_without_safety_claim():
    from src.agent.nlu import extract
    from src.agent.dialogue_memory import apply
    text='Реактор 90 литров, рабочий объём 100 литров, 5 кг пищевых отходов.'
    state=apply(DialogueState(),extract(text),tolerate_engineering_conflicts=True)
    result=analytical.scientific(analytical.context(state))
    assert result['scenarios'][0]['methane_m3']['low']>0
    assert result['scenarios'][0]['engineering']['status']=='PHYSICALLY_INFEASIBLE'
    assert state.advanced['input_conflicts']


def test_process_hypothesis_does_not_become_a_confirmed_water_addition():
    from src.agent.dialogue_memory import fact
    state=DialogueState(facts={'material':fact('food_waste'),'mass_kg':fact(5)},assumptions={'dilution_water_l':fact(10,provenance='ASSUMED_FOR_SCENARIO')})
    data=analytical.context(state)
    result=analytical.scientific(data)
    assert 'dilution_water_l' not in state.facts
    assert result['scenarios'][0]['engineering']['water_density_assumption_kg_l']==1
    assert any('hypothetical process input' in note for note in result['scenarios'][0]['assumptions'])


def test_concentration_without_added_water_is_defined():
    from src.agent.dilution import calculate_vs_concentration
    result=calculate_vs_concentration({'mass_kg':10,'vs_mass_kg':2,'dilution_water_l':0})
    assert result['status']=='ok' and result['vs_percent_wet_mass']==20


def test_density_label_does_not_swallow_a_later_reactor_capacity():
    from src.agent.nlu import extract
    result=extract('Есть 48 кг пищевых отходов, плотность 0.8 кг/л, реактор 90 литров.')
    values={e.name:e.value for e in result.entities}
    assert values['quantity']==48 and values['density_kg_l']==.8 and values['reactor_total_volume_l']==90


@pytest.mark.parametrize('text,animal,profile',[('9 кг козьего навоза','goat','eftaxias2024-goat'),('12 кг овечьего навоза','sheep','eftaxias2024-sheep')])
def test_species_is_preserved_inside_the_shared_sheep_goat_category(text,animal,profile):
    from src.agent.mixture_parser import explicit_components
    components=explicit_components(text)
    assert components[0].animal==animal
    data={'facts':{},'components':[c.model_dump(mode='json') for c in components],'decision':{},'mode':'mixture','language':'ru'}
    science=analytical.scientific(data)
    assert all(s['profile_ids']==[profile] for s in science['scenarios'])


def test_sentence_punctuation_does_not_change_the_operating_mode():
    from src.agent.nlu import extract
    from src.agent.process_bridge import augment
    state=DialogueState()
    result=augment('operating_mode=batch. Можно загрузить?',state,extract('operating_mode=batch. Можно загрузить?',state))
    assert any(e.name=='operating_mode' and e.value=='batch' for e in result.entities)


def test_failed_model_uses_one_explicit_bounded_local_fallback(tmp_path):
    from src.agent.providers import JSONProvider,HybridLLM,ProviderError
    from src.agent.conversation import ConversationAgent
    from src.agent.tools import ToolRegistry
    from src.market.store import Store
    calls=[]
    provider=JSONProvider('offline',model='qwen3:8b')
    def fail(*args):
        calls.append(True);raise ProviderError('TEST provider unavailable')
    provider.extract_dialogue=fail
    agent=ConversationAgent(research_enabled=True,llm=HybridLLM('offline',providers=[provider]),registry=ToolRegistry(Store(tmp_path/'fallback.sqlite3')))
    result=agent.ask('У меня 5 кг пищевых отходов и реактор 90 литров. Сколько метана и выгодно ли?')
    assert calls==[True]
    assert result['mode']=='deterministic_partial_provider_failure'
    assert '0.31814' in result['answer'] and 'Языковая модель недоступна' in result['answer']
    assert result['technical_metadata']['analytical_unchecked_tools']==[]
    assert len(result['tools'])==2


def test_word_quantity_preserves_literal_evidence_and_binds_mixture():
    from src.agent.nlu import extract
    from src.agent.mixture_parser import explicit_components
    parsed=extract('Пять кг пищевых отходов.')
    quantity=next(e for e in parsed.entities if e.name=='quantity')
    assert quantity.value==5 and quantity.evidence=='Пять кг'
    rows=explicit_components('Пять кг пищевых отходов и два кг свиного навоза')
    assert [(r.material,r.quantity) for r in rows]==[('food_waste',5),('swine_manure',2)]


def test_guarantee_request_checks_literature_without_assigning_its_sample_to_batch():
    from src.agent.dialogue_memory import fact
    from src.agent.autonomous import _unsupported_conclusions,_fallback_answer
    state=DialogueState(facts={'material':fact('food_waste'),'quantity':fact(4),'unit':fact('kg')})
    assert analytical.obligations(state,'Назови гарантированный результат без допущений')==['search_substrate_profiles']
    results={'search_substrate_profiles':search(['food_waste'])}
    assert _unsupported_conclusions('Данные о выходе метана BMP отсутствуют.',results)
    assert 'опубликованные профили' in _fallback_answer(results,state)


def test_model_quantity_question_is_retained_once_in_structured_memory():
    state=DialogueState()
    facing={'paragraphs':['Профили доступны. Какова масса партии?'],'sections':[],'question':None}
    result,body,_=finish_turn(state,'Оцени пищевые отходы',Extraction(),facing,'Профили доступны. Какова масса партии?',{})
    assert result['question']['id']=='batch-quantity'
    assert body.count('?')==1 and state.pending_question.id=='batch-quantity'
    result,body,diagnostics=finish_turn(state,'Не знаю',Extraction(),{'paragraphs':[],'sections':[],'question':None},'Какова масса партии?',{})
    assert result['question'] is None and '?' not in body
    assert diagnostics[0]['reason']=='repeated_question_suppressed'


def test_public_metadata_respects_offline_mode_without_http(monkeypatch):
    from src.research import public_metadata
    monkeypatch.setenv('BIOREACTOR_RESEARCH_ONLINE','0')
    monkeypatch.setattr(public_metadata,'urlopen',lambda *a,**k:pytest.fail('Offline research must not issue HTTP'))
    result=public_metadata.search(['food_waste'])
    assert result['live_search_performed'] is False and result['sources']==[]


def test_local_economics_recovery_reuses_existing_science(tmp_path):
    from src.market.store import Store
    data={'facts':{'material':'food_waste','mass_kg':5},'components':[],'decision':{},'mode':'mixture','language':'ru'}
    science=analytical.scientific(data)
    result=execute('recover_partial_economics',{'analytical_context':data},{'assess_substrate_potential':science},'',Store(tmp_path/'recovery.sqlite3'))
    assert result['scenarios'][0]['analysis']['energy']['outputs']['potential_fuel_kwh']['low']>0
    assert result['profit_established'] is False


def test_missing_identity_does_not_erase_a_known_batch_mass():
    result=analytical.scientific({'facts':{'mass_kg':5},'components':[],'decision':{},'mode':'mixture','language':'ru'})
    assert result['known_quantity']==5 and 'batch_quantity' not in result['missing']
    result=analytical.scientific({'facts':{'material':'food_waste'},'components':[],'decision':{},'mode':'mixture','language':'ru'})
    assert result['available_profile_ids'] and result['missing']==['batch_quantity']


def test_affirmative_loading_claim_cannot_override_impossible_geometry():
    from src.agent.autonomous import _unsupported_conclusions
    results={'assess_substrate_potential':{'scenarios':[{'engineering':{'status':'PHYSICALLY_INFEASIBLE'}}]}}
    assert 'loading_conclusion_contradicts_calculated_capacity' in _unsupported_conclusions('Можно загрузить эту партию.',results)


def test_input_numbers_do_not_count_as_a_computed_answer():
    from src.agent.autonomous import _mentions_calculated_quantity
    values=[{'low':.3181407,'high':.3181407}]
    assert not _mentions_calculated_quantity('У вас 5 кг и реактор 90 л. Требуются дополнительные параметры.',values,r'м³|m3')
    assert _mentions_calculated_quantity('Условный потенциал 0.32 м³ CH4.',values,r'м³|m3')
    assert not _mentions_calculated_quantity('Будет 0 м³.',values,r'м³|m3')


def test_conditional_net_result_range_is_rendered_without_a_scalar_cast():
    # Test-only structured result; no price or experiment is added to a store.
    result={'evaluate_partial_economics':{'profit_established':False,'scenarios':[{'analysis':{'energy':{'outputs':{}},'prices':{},'scenarios':[{'id':'B_heat','net_result_kzt':{'low':10,'high':20}}]}}]}}
    facing=analytical.user_facing(result,DialogueState())
    economy=facing['sections'][3]['body']
    assert '10' in economy and '20' in economy and 'KZT' in economy and 'Условный' in economy
