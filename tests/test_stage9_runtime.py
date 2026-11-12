"""Protocol/fault fixtures; these are not real-Qwen acceptance measurements."""
import json
from src.agent import analytical
from src.agent.conversation import ConversationAgent
from src.agent.dialogue_types import NLUProposal
from src.agent.providers import HybridLLM,JSONProvider
from src.agent.tools import ToolRegistry

def agent_with(decide,registry=None):
    provider=JSONProvider('offline',model='qwen3:8b')
    provider.extract_dialogue=lambda *args:NLUProposal(language='ru',intents=['methane_yield'],material=None,material_evidence=None,entities=[])
    provider.generate=decide
    agent=ConversationAgent(research_enabled=True,llm=HybridLLM('offline',providers=[provider]),registry=registry or ToolRegistry())
    agent.runtime_version='9'
    return agent

def action(tool=None):return {'action':'tool' if tool else 'answer','tool':tool or '','arguments':{},'purpose':'TEST protocol action'}
def synthesis(payload):
    return {'conclusion':'Получен условный потенциал метана.','explanation':'Это расчёт по опубликованному образцу, а не измеренная выработка установки.',
            'limitations':['Условия переноса на вашу партию не подтверждены.'],'next_question':None,
            'evidence_ids':[k for k in payload['evidence'] if k.endswith('.methane')][:2],'decision':'not_applicable'}

def test_v9_uses_model_selected_tools_then_independently_verified_synthesis():
    decisions=iter([action('assess_substrate_potential'),action()])
    def decide(messages,schema):
        return next(decisions) if 'action' in schema['properties'] else synthesis(json.loads(messages[-1]['content']))
    reply=agent_with(decide).ask('У меня 5 кг пищевых отходов. Сколько метана?')
    assert reply['technical_metadata']['final_author']=='qwen_verified'
    assert reply['technical_metadata']['verification']['status']=='ok'
    assert [t['tool'] for t in reply['tools']]==['assess_substrate_potential']
    assert 'м³ CH₄' in reply['answer'] and reply['actuator_access'] is False

def test_model_cannot_bypass_primary_evidence_gate():
    schemas=[]
    def decide(messages,schema):schemas.append(schema);return action()
    reply=agent_with(decide).ask('У меня 5 кг пищевых отходов. Сколько метана?')
    assert reply['technical_metadata']['final_author']=='verified_engine_partial'
    assert reply['technical_metadata']['primary_evidence_unchecked']==[]
    assert reply['tools'][0]['tool']=='assess_substrate_potential' and reply['tools'][0]['input_origin']=='controller_required_evidence'
    assert all(s['properties']['action']['enum']==['tool'] for s in schemas if 'action' in s['properties'])

def test_failed_scientific_tool_can_replan_to_alternative_path():
    class FaultRegistry(ToolRegistry):
        def _execute(self,name,*args):
            if name=='assess_substrate_potential':return {'status':'error','message':'TEST controlled scientific adapter failure'}
            return super()._execute(name,*args)
    decisions=iter([action('assess_substrate_potential'),action('recover_local_scientific_analysis'),action()])
    def decide(messages,schema):
        return next(decisions) if 'action' in schema['properties'] else synthesis(json.loads(messages[-1]['content']))
    reply=agent_with(decide,FaultRegistry()).ask('Есть 5 кг пищевых отходов. Сколько метана?')
    assert [t['status'] for t in reply['tools']]==['error','ok']
    assert reply['technical_metadata']['final_author']=='qwen_verified' and 'м³ CH₄' in reply['answer']


def test_unchecked_ok_cannot_admit_numeric_synthesis_or_verified_display(monkeypatch):
    decisions=iter([action('assess_substrate_potential'),action()]);synthesis_calls=[]
    def decide(messages,schema):
        if 'action' in schema['properties']:return next(decisions)
        synthesis_calls.append(True);return synthesis(json.loads(messages[-1]['content']))
    monkeypatch.setattr('src.agent.runtime9.verify_results',lambda _: {'status':'ok','checked':False,'all_checks_passed':False,'checks':[]})
    reply=agent_with(decide).ask('У меня 5 кг пищевых отходов. Сколько метана?')
    assert not synthesis_calls and reply['technical_metadata']['final_author']!='qwen_verified'
    assert not reply['technical_metadata']['verified_display_references']


def test_information_without_arithmetic_can_answer_without_numeric_verification_label():
    def decide(messages,schema):
        if 'action' in schema['properties']:return action()
        return {'conclusion':'Анаэробный процесс протекает без кислорода.',
                'explanation':'Это определение, а не численный расчёт.',
                'limitations':[],'next_question':None,'evidence_ids':[],'decision':'not_applicable'}
    agent=agent_with(decide)
    agent.llm.providers[0].extract_dialogue=lambda *args:NLUProposal(language='ru',intents=[],material=None,material_evidence=None,entities=[])
    reply=agent.ask('Объясни термин «анаэробный процесс».')
    assert reply['technical_metadata']['final_author']=='qwen_grounded_information'
    assert reply['technical_metadata']['verification']['status']=='not_applicable'
    assert reply['technical_metadata']['verification']['checked'] is False
    assert reply['user_facing_answer']['modes']==['model_information_not_numeric_verification']


def test_failed_model_selection_still_checks_available_required_batch_evidence():
    from src.agent.providers import ProviderError
    def broken(*args):raise ProviderError('TEST early selection failure')
    reply=agent_with(broken).ask('Сколько денег я заработаю на 5 кг пищевых отходов?')
    assert {t['tool'] for t in reply['tools']} >= {'assess_substrate_potential','evaluate_partial_economics'}
    assert not reply['technical_metadata']['primary_evidence_unchecked']
    assert reply['technical_metadata']['final_author']=='verified_engine_partial'
    assert any(r['id'].endswith('.methane') for r in reply['technical_metadata']['verified_display_references'])
    assert any(r['id'].endswith('.gross') or r['id'].endswith('_kwh') for r in reply['technical_metadata']['verified_display_references'])
    assert reply['answer'].startswith('Предварительная оценка по доступным данным:')
    assert 'Модель не завершила' not in reply['answer']


def test_required_preflight_respects_tool_budget(monkeypatch):
    from src.agent.providers import ProviderError
    monkeypatch.setenv('BIOREACTOR_AGENT_MAX_TOOLS','1')
    def broken(*args):raise ProviderError('TEST selection failure with strict budget')
    reply=agent_with(broken).ask('Сколько денег я заработаю на 5 кг пищевых отходов?')
    assert len(reply['tools'])==1
    assert reply['technical_metadata']['primary_evidence_unchecked']==['evaluate_partial_economics']
    assert any(d.get('reason')=='resource_budget_exhausted' for d in reply['technical_metadata']['diagnostics'])


def test_required_preflight_does_not_invent_missing_material_properties():
    from src.agent.providers import ProviderError
    def broken(*args):raise ProviderError('TEST no applicable batch')
    reply=agent_with(broken).ask('Сколько метана из неизвестного сырья?')
    assert reply['tools'][0]['result']['status']=='needs_input'
    assert reply['tools'][0]['result']['scenarios']==[]
    assert not reply['technical_metadata']['verified_display_references']


def test_process_fallback_returns_existing_qualitative_analysis():
    from src.agent.providers import ProviderError
    def broken(*args):raise ProviderError('TEST failed model synthesis')
    agent=agent_with(broken)
    agent.llm.providers[0].extract_dialogue=lambda *args:NLUProposal(language='ru',intents=['temperature_recommendation'],material=None,material_evidence=None,entities=[])
    reply=agent.ask('В реакторе 30 градусов. Стоит ли повышать температуру?')
    assert '30' in reply['answer'] and 'сама по себе не обосновывает' in reply['answer']
    assert reply['answer'].count('?')==1
    assert reply['technical_metadata']['verification']['status']=='not_applicable'


def test_dilution_water_requires_process_evidence_and_explains_its_scope():
    from src.agent.dialogue_memory import fact,from_context
    from src.agent.runtime9 import requirements,fallback_explanations
    state=from_context({'material':'food_waste','mass_kg':5});state.intents=['methane_yield']
    state.assumptions['dilution_water_l']=fact(10,'L','ASSUMED_FOR_SCENARIO','TEST hypothetical clean water')
    assert 'assess_process_evidence' in requirements(state,'Если добавить 10 литров воды, метана станет больше?')
    process=analytical.process(analytical.context(state))
    text=' '.join(fallback_explanations({'assess_process_evidence':process},state))
    assert '10 л чистой воды' in text and '0 кг VS' in text and 'потенциала CH₄' in text
    assert 'не увеличивается' in text and 'Разбавление меняет концентрацию' in text
    assert 'опубликованные опыты' not in text and '°C' not in text


def test_unknown_substrate_fallback_names_missing_identity_not_scenarios():
    from src.agent.dialogue_memory import from_context
    from src.agent.runtime9 import fallback_explanations
    state=from_context({'mass_kg':5});state.intents=['methane_yield']
    text=' '.join(fallback_explanations({'assess_substrate_potential':{
        'status':'needs_input','scenarios':[],'missing':['material_identity_or_component_inventory']}},state))
    assert 'Вид сырья или состав смеси не определён' in text
    assert 'TS, VS и BMP' in text and 'Какие именно отходы' in text


def test_unknown_substrate_question_is_preserved_as_structured_clarification():
    from types import SimpleNamespace
    from src.agent.dialogue_memory import from_context
    from src.agent.research_memory import finish_turn
    state=from_context({'mass_kg':5});state.intents=['methane_yield']
    explanation='Вид сырья или состав смеси не определён. Без этого нельзя выбрать TS, VS и BMP. Какие именно отходы вы планируете сбраживать?'
    facing={'paragraphs':[explanation],'sections':[],'question':None}
    proposal=SimpleNamespace(correction=False,intents=['methane_yield'],entities=[])
    facing,answer,_=finish_turn(state,'У меня 5 кг неизвестного органического сырья, сколько метана?',proposal,
                                facing,explanation,{})
    assert facing['question']['text']=='Какие именно отходы вы планируете сбраживать?'
    assert answer.count('?')==1 and answer.endswith(facing['question']['text'])


def test_comparison_fallback_distinguishes_methane_potential_from_profit():
    from src.agent.dialogue_memory import from_context
    from src.agent.runtime9 import fallback_explanations
    state=from_context({'material':'food_waste','mass_kg':10});state.intents=['economic_comparison']
    text=' '.join(fallback_explanations({'evaluate_partial_economics':{
        'potential_dominates_other_material_scenarios':['Пищевые отходы'],'profit_established':False}},state))
    assert 'больший расчётный потенциал метана у Пищевые отходы' in text
    assert 'чистую прибыль' in text and 'определить нельзя' in text


def test_runtime_allows_distinct_search_inputs_and_blocks_normalized_repeat():
    from src.agent.runtime9 import tool_invocation_key
    from src.agent.dialogue_memory import from_context
    context={'analytical_context':{'facts':{},'components':[]}}
    key=tool_invocation_key('search_substrate_profiles',context,{},'Wheat  straw')
    assert key==tool_invocation_key('search_substrate_profiles',context,{},' wheat STRAW ')
    assert key!=tool_invocation_key('search_substrate_profiles',context,{},'food waste')
    known={'analytical_context':analytical.context(from_context({'material':'food_waste'}))}
    assert tool_invocation_key('search_substrate_profiles',known,{},'food waste')==tool_invocation_key(
        'search_substrate_profiles',known,{},'another phrase')

    def exercise(queries):
        provider=JSONProvider('offline',model='qwen3:8b')
        provider.extract_dialogue=lambda *args:NLUProposal(language='ru',intents=[],material=None,material_evidence=None,entities=[])
        choices=iter([{'action':'tool','tool':'search_substrate_profiles','arguments':{'query':query},
                       'purpose':'TEST distinct retrieval query','ready_after_tool':False} for query in queries])
        if len(set(queries))==len(queries):
            choices=iter(list(choices)+[{'action':'answer','tool':'','arguments':{},'purpose':'TEST finish','ready_after_tool':False}])
        def generate(messages,schema):
            if 'action' in schema['properties']:return next(choices)
            return {'conclusion':'Проверены отдельные досье.','explanation':'Выход установки не прогнозировался.',
                'limitations':['Условия партии не проверены.'],'next_question':None,'evidence_ids':[],'decision':'not_applicable'}
        provider.generate=generate
        agent=ConversationAgent(research_enabled=True,llm=HybridLLM('offline',providers=[provider]));agent.runtime_version='9'
        calls=[];execute=agent.registry.execute
        def counted(name,context,results,query):
            if name=='search_substrate_profiles':calls.append(query)
            return execute(name,context,results,query)
        agent.registry.execute=counted
        return agent.ask('Найди научные профили сырья.'),calls

    distinct,calls=exercise(['Wheat straw','food waste'])
    assert calls==['Wheat straw','food waste']
    dossiers=distinct['technical_metadata']['scientific_details']['search_substrate_profiles']['dossiers']
    assert {row['material'] for row in dossiers}=={'straw','food_waste'}
    repeated,calls=exercise(['Wheat  straw',' wheat STRAW '])
    assert calls==['Wheat  straw']
    assert any(d.get('reason')=='repeated_tool_input_blocked' for d in repeated['technical_metadata']['diagnostics'])
