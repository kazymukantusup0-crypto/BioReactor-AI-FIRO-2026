"""Partial evidence must lead to scoped calculations, never invented inputs."""
import copy
import pytest
from src.agent import analytical
from src.agent.dialogue_types import DialogueState,NLUProposal
from src.agent.providers import HybridLLM,JSONProvider
from src.agent.conversation import ConversationAgent
from src.agent.tools import ToolRegistry
from src.market.store import Store


def data(material='food_waste',mass=5):
    return {'facts':{'material':material,'mass_kg':mass},'components':[],
            'decision':{},'mode':'mixture','language':'ru'}


def test_conditional_food_keeps_confirmed_inputs_and_source_point():
    d=data();original=copy.deepcopy(d);r=analytical.scientific(d)
    s=r['scenarios'][0]
    assert d==original
    assert s['profile_ids']==['baek2020-food-pulp']
    assert s['vs_mass_kg']['low']==pytest.approx(.603)
    assert s['methane_m3']['low']==pytest.approx(5*.1206*527.5*.001*273.2/273.15)
    assert s['methane_m3']['low']==s['methane_m3']['high']
    assert s['result_level']=='HYPOTHETICAL_SCENARIO'
    assert s['biogas']['potential_biogas_m3'] is None


def test_unknown_properties_do_not_create_numbers():
    r=analytical.scientific(data('other_organic'))
    assert r['status']=='needs_input'
    assert all(s['methane_m3'] is None for s in r['scenarios'])


def test_pig_studies_separate_and_no_unmeasured_biogas_fraction():
    r=analytical.scientific(data('swine_manure',8))
    assert len(r['scenarios'])>=2
    for s in r['scenarios']:
        assert s['methane_m3']['low']>0
        assert s['assumptions']
        assert s['biogas']['potential_biogas_m3'] is None


def test_alternatives_not_a_mixture():
    d=data();d['mode']='alternatives';d['components']=[
        {'id':'c1','material':'cattle_manure','quantity':10},
        {'id':'c2','material':'food_waste','quantity':10}]
    r=analytical.scientific(d)
    assert all(s['wet_mass_kg']['low']==10 for s in r['scenarios'])
    assert all(len(s['components'])==1 for s in r['scenarios'])


def test_missing_prices_and_costs_preserve_energy(tmp_path):
    d=data();science=analytical.scientific(d)
    result=analytical.economics(d,{'assess_substrate_potential':science},Store(tmp_path/'empty.sqlite3'))
    a=result['scenarios'][0]['analysis']
    assert a['energy']['outputs']['potential_fuel_kwh']['low']>0
    assert a['operating_costs']['complete_total'] is None
    assert all(s['net_result_kzt'] is None for s in a['scenarios'])
    answer=analytical.render({'assess_substrate_potential':science,'evaluate_partial_economics':result},DialogueState(language='ru'))
    assert '× P' in answer
    assert answer.count('?')==1


def test_saved_region_is_not_asked_again_and_compact_answer_separates_details(tmp_path):
    from src.agent.dialogue_memory import fact
    d=data();science=analytical.scientific(d)
    economics=analytical.economics(d,{'assess_substrate_potential':science},Store(tmp_path/'empty.sqlite3'))
    state=DialogueState(language='ru')
    state.facts['market_region']=fact('KZ-Karaganda-oblast',evidence='В Карагандинской')
    result={'assess_substrate_potential':science,'evaluate_partial_economics':economics}
    answer=analytical.render(result,state)
    assert 'В каком регионе находится установка?' not in answer
    assert 'Какие полные расходы' in answer
    facing=analytical.user_facing(result,state)
    assert [section['title'] for section in facing['sections']]==['Краткий результат','Потенциал метана','Энергетическая ценность','Экономика','Ограничения и риски']
    assert facing['question']['id']=='operating-costs'
    primary=' '.join(section['body'] for section in facing['sections'])
    assert 'BMP' not in primary and 'мл CH₄/г VS' not in primary
    assert len(facing['sources'])==1


def test_region_clarification_is_requested_only_when_unconfirmed(tmp_path):
    science=analytical.scientific(data())
    economics=analytical.economics(data(),{'assess_substrate_potential':science},Store(tmp_path/'empty.sqlite3'))
    facing=analytical.user_facing({'assess_substrate_potential':science,'evaluate_partial_economics':economics},DialogueState())
    assert facing['question']['id']=='market-region'


def test_refusal_cannot_skip_calculation_tools(tmp_path):
    p=JSONProvider('offline',model='qwen3:8b')
    p.extract_dialogue=lambda text,memory:NLUProposal(language='ru',intents=['methane_yield','economic_comparison'],material=None,material_evidence=None,entities=[])
    first=True
    def action(question,facts,memory,history,observations,allowed_tools,final_only=False):
        nonlocal first
        if first:first=False;return {'action':'final','tool':None,'arguments':{},'final':'Недостаточно данных.'}
        pending=memory.get('required_tool_checks',[])
        if pending:return {'action':'call_tool','tool':allowed_tools[0],'arguments':{},'final':''}
        return {'action':'final','tool':None,'arguments':{},'final':'Недостаточно данных.'}
    p.autonomous_action=action
    a=ConversationAgent(llm=HybridLLM('offline',providers=[p]),registry=ToolRegistry(Store(tmp_path/'db.sqlite3')),research_enabled=True)
    r=a.ask('У меня 5 кг пищевых отходов и реактор 90 литров. Сколько метана и выгодно ли?')
    assert [t['tool'] for t in r['tools']]==['assess_substrate_potential','evaluate_partial_economics']
    assert '0.31814' in r['answer']
    assert '90 л' in r['answer']
    assert r['technical_metadata']['analytical_unchecked_tools']==[]
    assert r['technical_metadata']['diagnostics'][0]['reason']=='calculation_evidence_not_checked'


def test_water_is_not_a_feed_quantity_or_edit():
    from src.agent.nlu import extract
    from src.agent.mixture_parser import parse_turn
    state=DialogueState(language='ru',mixture_components=[{'id':'c1','material':'food_waste','quantity':5,'unit':'kg'}])
    text='Если я добавлю 10 литров воды, метана станет больше?'
    assert parse_turn(text,state) is None
    parsed=extract(text,state)
    fields={e.name:e.value for e in parsed.entities}
    assert fields['dilution_water_l']==10
    assert 'quantity' not in fields
    assert analytical.process({'facts':fields})['added_water_methane_potential_m3']==0


def test_measured_properties_keep_their_own_gas_basis():
    d=data();d['components']=[{'id':'c1','material':'food_waste','quantity':5,'data_mode':'MEASURED',
        'properties':{'ts_fraction':.2,'vs_fraction_wet':.1,'bmp_ml_g_vs':300,
            'gas_basis':{'temperature_k':293.15,'pressure_pa':101325,'moisture':'wet'}}}]
    r=analytical.scientific(d);s=r['scenarios'][0]
    assert s['methane_m3']['low']==pytest.approx(.15)
    assert s['gas_basis']['moisture']=='wet'
    assert s['profile_ids']==[None]
    assert not s['assumptions']
    assert 'по опубликованным образцам' not in analytical.render({'assess_substrate_potential':r},DialogueState(language='ru'))


def test_tool_failure_is_not_an_evidence_absence():
    r={'assess_substrate_potential':{'status':'error','message':'TEST source unavailable'}}
    answer=analytical.render(r,DialogueState(language='ru'))
    assert 'TEST source unavailable' in answer
    assert 'Каталог проверен' not in answer


@pytest.mark.parametrize('language',['en','kk'])
def test_new_calculations_keep_existing_ui_languages(language):
    r={'assess_substrate_potential':analytical.scientific(data())}
    answer=analytical.render(r,DialogueState(language=language))
    assert '0.31814' in answer
    assert 'Пищевые отходы' not in answer
    assert answer.count('?')==1
