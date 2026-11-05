import pytest

from src.agent.conversation import ConversationAgent
from src.agent.dialogue_types import NLUProposal
from src.agent.providers import HybridLLM,JSONProvider,ProviderError
from src.agent.tools import ToolRegistry


def test_local_llm_can_select_sequential_read_only_tools(monkeypatch):
    provider=JSONProvider('offline',model='qwen3:8b')
    provider.extract_dialogue=lambda text,memory:NLUProposal(language='en',intents=['model_info','sources'],
        material=None,material_evidence=None,entities=[])
    actions=iter([
        {'action':'call_tool','tool':'search_scientific_sources','arguments':{},'final':''},
        {'action':'call_tool','tool':'get_model_info','arguments':{},'final':''},
        {'action':'final','tool':None,'arguments':{},'final':'The local search returned no matching source; the model metrics describe laboratory evaluation.'},
    ])
    seen=[]
    def next_action(question,facts,memory,history,observations,allowed_tools,final_only=False):
        seen.append((list(allowed_tools),final_only,len(observations)))
        return next(actions)
    provider.autonomous_action=next_action
    llm=HybridLLM('offline',providers=[provider])
    agent=ConversationAgent(research_enabled=True,llm=llm,registry=ToolRegistry())
    result=agent.ask('Show reviewed scientific sources and the BMP model evaluation.')
    assert result['mode']=='qwen_autonomous_tools'
    assert [row['tool'] for row in result['tools']]==['search_scientific_sources','get_model_info']
    assert result['actuator_access'] is False
    assert seen[1][0] and 'search_scientific_sources' not in seen[1][0]
    assert seen[2][2]==2


def test_action_arguments_cannot_inject_measurements():
    provider=JSONProvider('offline',model='qwen3:8b')
    provider.generate=lambda *args,**kwargs:{'action':'call_tool','tool':'search_scientific_sources',
        'arguments':{'query':'BMP','mass_kg':999},'final':''}
    with pytest.raises(ProviderError,match='Invalid autonomous action schema'):
        provider.autonomous_action('question',{}, {},[],[],['search_scientific_sources'])


def test_numeric_answer_guard_rejects_unavailable_values():
    from src.agent.autonomous import _numbers_are_grounded
    agent=ConversationAgent(llm=HybridLLM(providers=[]))
    assert _numbers_are_grounded('No live readings are available.',agent.state,{})
    assert not _numbers_are_grounded('The reactor temperature is 37 C.',agent.state,{})


def test_grounded_fallback_is_checked_as_the_final_answer():
    from src.agent.autonomous import _fallback_answer,_numbers_are_grounded
    from src.agent.dialogue_types import DialogueState
    agent=ConversationAgent(state=DialogueState(language='en'),llm=HybridLLM(providers=[]))
    results={'estimate_advanced_gas':{'mixture':{
        'total_wet_mass_kg':{'low':9.0,'high':9.0},
        'known_component_additive_subtotal_m3':{'low':0.1618,'high':0.1618},
        'complete_methane_reference':False,
        'components':[{'material':'wheat_straw','methane_reference_m3':{'low':0.1618,'high':0.1618}},
            {'material':'food_waste','missing':['TS','VS','BMP']}]}}
    }
    final=_fallback_answer(results,agent.state)
    assert '9 kg' in final
    assert '0.1618' in final
    assert _numbers_are_grounded(final,agent.state,results)


def test_partial_mixture_fallback_keeps_known_component_scope():
    from src.agent.autonomous import _fallback_answer,_unsupported_units
    from src.agent.dialogue_types import DialogueState
    results={'estimate_advanced_gas':{'mixture':{
        'complete_methane_reference':False,
        'known_component_additive_subtotal_m3':{'low':0.2438,'high':0.2438},
        'components':[]}}}
    answer=_fallback_answer(results,DialogueState(language='en'))
    assert 'Only components with comparable data' in answer
    assert _unsupported_units(answer,results)==[]


def test_numeric_grounding_accepts_display_rounding_but_not_different_values():
    from src.agent.autonomous import _unsupported_numbers
    from src.agent.dialogue_types import DialogueState
    evidence={'value':0.24383999999999997}
    state=DialogueState(language='en')
    assert _unsupported_numbers('Known component subtotal: 0.2438 m3.',state,evidence)==[]
    assert _unsupported_numbers('Known component subtotal: 0.29 m3.',state,evidence)==['0.29']


def test_vs_concentration_tool_uses_mass_basis_and_discloses_water_assumption():
    from src.agent.dilution import calculate_vs_concentration
    result=calculate_vs_concentration({'vs_mass_kg':2,'mass_kg':10,'dilution_water_l':5})
    assert result['status']=='ok'
    assert result['total_wet_mass_after_dilution_kg']==15
    assert result['vs_percent_wet_mass']==pytest.approx(100*2/15)
    assert result['volumetric_concentration_kg_vs_m3'] is None
    assert '1.0 kg/L' in result['assumptions'][0]


def test_vs_concentration_tool_reports_missing_inputs():
    from src.agent.dilution import calculate_vs_concentration
    result=calculate_vs_concentration({'vs_mass_kg':2})
    assert result['status']=='needs_input'
    assert result['missing']==['mass_kg','dilution_water_l']


def test_qwen_tool_loop_can_calculate_diluted_vs_concentration():
    provider=JSONProvider('offline',model='qwen3:8b')
    provider.extract_dialogue=lambda text,memory:NLUProposal(language='en',intents=['process_guidance'],
        material=None,material_evidence=None,entities=[])
    actions=iter([
        {'action':'call_tool','tool':'calculate_vs_concentration','arguments':{},'final':''},
        {'action':'final','tool':None,'arguments':{},'final':'On a wet-mass basis, VS is 13.3% after dilution, assuming water density of 1 kg/L. A volumetric concentration needs feed volume or density.'},
    ])
    provider.autonomous_action=lambda *args,**kwargs:next(actions)
    agent=ConversationAgent(research_enabled=True,llm=HybridLLM('offline',providers=[provider]),registry=ToolRegistry())
    result=agent.ask('My 10 kg feed contains 2 kg volatile solids. If I add 5 litres of water, calculate VS concentration.')
    assert result['mode']=='qwen_autonomous_tools'
    assert result['tools'][0]['tool']=='calculate_vs_concentration'
    assert result['tools'][0]['status']=='ok'
    assert '13.3%' in result['answer']
    assert '1 kg/L' in result['answer']
    assert 'volumetric concentration needs feed volume or density' in result['answer']
    assert result['technical_metadata']['numeric_claims_grounded'] is True


def test_fallback_requests_manure_form_without_claiming_a_yield():
    from src.agent.autonomous import _fallback_answer
    from src.agent.dialogue_types import DialogueState
    from src.advisor.schemas import Component
    component=Component(id='c1',material='cattle_manure',quantity=5,unit='kg').model_dump(mode='json')
    state=DialogueState(language='en',mixture_components=[component])
    answer=_fallback_answer({},state)
    assert 'physical form' in answer
    assert 'estimate methane' in answer
    assert 'm³' not in answer


def test_single_substrate_tool_context_uses_only_confirmed_batch_facts():
    from datetime import datetime,timezone
    from src.agent.autonomous import _available_tools,_tool_context
    from src.agent.dialogue_types import DialogueState,Fact
    now=datetime.now(timezone.utc).isoformat()
    state=DialogueState(language='en',intents=['methane_yield'])
    state.facts={
        'material':Fact(value='food_waste',provenance='USER_CONFIRMED',evidence='4 kg food waste',recorded_at=now),
        'quantity':Fact(value=4,unit='kg',provenance='USER_CONFIRMED',evidence='4 kg food waste',recorded_at=now),
        'unit':Fact(value='kg',provenance='USER_CONFIRMED',evidence='4 kg food waste',recorded_at=now),
    }
    agent=ConversationAgent(state=state,llm=HybridLLM(providers=[]))
    assert 'estimate_substrate_gas' in _available_tools(agent.state)
    request=_tool_context(agent,'estimate_substrate_gas','estimate',{})['advisor_request']
    assert request['components'][0]['material']=='food_waste'
    assert request['components'][0]['quantity']==4
    assert request['components'][0]['unit']=='kg'


def test_substrate_advisor_tools_are_not_offered_without_batch_quantity():
    from src.agent.autonomous import _available_tools
    from src.agent.dialogue_types import DialogueState
    state=DialogueState(language='en',intents=['temperature_recommendation'])
    agent=ConversationAgent(state=state,llm=HybridLLM(providers=[]))
    assert 'advise_substrate_conditions' not in _available_tools(agent.state)
    assert 'get_matched_substrate_conditions' not in _available_tools(agent.state)


def test_yield_tools_wait_for_required_manure_form_clarification():
    from src.agent.autonomous import _available_tools
    from src.agent.dialogue_types import DialogueState,Question
    from src.advisor.schemas import Component
    component=Component(id='c1',material='cattle_manure',quantity=20,unit='kg').model_dump(mode='json')
    state=DialogueState(language='en',intents=['methane_yield'],mixture_components=[component])
    agent=ConversationAgent(state=state,llm=HybridLLM(providers=[]))
    tools=_available_tools(agent.state)
    assert 'estimate_advanced_gas' not in tools
    agent.state.pending_question=Question(id='advanced-material-state',text='Select the manure form.',fields=['physical_state'])
    agent.state.mixture_components[0]['physical_state']='liquid'
    tools=_available_tools(agent.state)
    assert 'estimate_advanced_gas' in tools


@pytest.mark.parametrize('prompt',[
    'If I add clean water to a feed mixture, what changes in concentration?',
    'Our digester reading fell from 35 C to 24 C. What could explain it?',
])
def test_generic_change_language_is_not_misread_as_inventory_replacement(prompt):
    agent=ConversationAgent(research_enabled=True,llm=HybridLLM(providers=[]))
    result=agent.ask(prompt)
    assert result['mode']!='input_rejected'
    assert 'There is no confirmed inventory to edit' not in result.get('technical_metadata',{}).get('validation_errors',[])


def test_nlu_extracts_measured_bmp_vs_mass_and_explicit_gas_basis():
    from src.agent.nlu import extract
    result=extract('A lab reports 250 mL CH4/g VS on a 273.2 K, 1.01325 bar gas basis. '
        'The sample contains 2 kg measured VS. Calculate its methane reference.')
    values={row.name:row.value for row in result.entities}
    assert values['bmp_ml_ch4_g_vs']==250
    assert values['bmp_unit']=='mL CH4/g VS'
    assert values['vs_mass_kg']==2
    assert values['gas_volume_basis']=='273.2 K; 1.01325 bar; moisture not specified'
    assert 'reported_methane_volume_m3' not in values
    dilution=extract('My 10 kg feed contains 2 kg volatile solids. If I add 5 litres of water, calculate VS concentration.')
    assert 'process_guidance' in dilution.intents
    dilution_values=[(row.name,row.value) for row in dilution.entities]
    assert ('quantity',10.0) in dilution_values
    assert ('vs_mass_kg',2.0) in dilution_values
    assert ('dilution_water_l',5.0) in dilution_values
    assert ('quantity',5.0) not in dilution_values


def test_cattle_slurry_alias_is_a_confirmed_cattle_manure_material():
    from src.agent.nlu import extract
    result=extract('I have 10 kg cattle slurry.')
    values={row.name:row.value for row in result.entities}
    assert values['material']=='cattle_manure'
    assert values['quantity']==10
    assert values['unit']=='kg'


def test_measured_vs_is_not_parsed_as_an_unbound_mixture_component():
    from src.agent import mixture_parser
    from src.agent.dialogue_types import DialogueState
    text='I have 12 kg cattle slurry and 2 kg food waste; a lab measured 3 kg VS in the combined sample.'
    parsed=mixture_parser.parse_turn(text,DialogueState())
    assert parsed is not None
    assert [component.material for component in parsed['components']]==['cattle_manure','food_waste']
    assert [component.quantity for component in parsed['components']]==[12,2]


def test_hypothetical_addition_can_extend_a_confirmed_single_substrate_batch():
    from src.agent import mixture_parser
    from src.agent.dialogue_types import DialogueState
    from src.advisor.schemas import Component
    component=Component(id='c1',material='cattle_manure',material_state='slurry',quantity=10,unit='kg').model_dump(mode='json')
    state=DialogueState(mixture_components=[component])
    parsed=mixture_parser.parse_turn('What if I add 2 kg food waste as a separate scenario?',state)
    assert parsed is not None and parsed['scenario'] is True
    assert [row.material for row in parsed['components']]==['cattle_manure','food_waste']


def test_scientific_evidence_tool_is_not_offered_without_a_material():
    from src.agent.autonomous import _available_tools
    from src.agent.dialogue_types import DialogueState
    tools=_available_tools(DialogueState(intents=['sources']))
    assert 'search_scientific_sources' in tools
    assert 'research_scientific_evidence' not in tools
