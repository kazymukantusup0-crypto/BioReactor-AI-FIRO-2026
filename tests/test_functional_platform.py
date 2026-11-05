"""v8.3 shared-evidence and geometry invariants; all explicit numeric inputs TEST ONLY."""
import main
import pytest
from src.advisor.schemas import AdvisorRequest
from src.advisor.service import analyze
from src.advisor.evidence_engine import scientific_request
from src.advisor.engineering import evaluate
from src.advisor import mixing,catalog
from src.agent import analytical,decision_bridge,nlu
from src.agent.dialogue_types import DialogueState
from src.agent.dialogue_memory import apply
from src.market.store import Store

def request(material='food_waste',quantity=5,**kwargs):
    return AdvisorRequest.model_validate({'components':[{'id':'c1','material':material,'quantity':quantity}],
        'allow_conditional_profiles':True,'assume_common_dry_gas_basis':True,**kwargs})

def test_shared_api_chat_and_unchanged_inventory(tmp_path):
    r=request();original=r.model_dump()
    api=analyze(Store(tmp_path/'test.sqlite3'),r,persist=False)
    chat=analytical.scientific({'facts':{},'components':original['components'],'decision':{},'mode':'mixture','advisor_settings':{'allow_conditional_profiles':True,'assume_common_dry_gas_basis':True}})
    assert r.model_dump()==original
    assert api['mixture']==chat['scenarios'][0]['mixture']
    assert api['engineering']==chat['scenarios'][0]['engineering']
    assert api['mixture']['additive_methane_reference_m3']['low']==pytest.approx(.318140715815)

def test_grass_pairs_not_artificial_interval():
    science=scientific_request(request('grass',58))
    assert len(science['scenarios'])==6
    assert not science['truncated']
    for s in science['scenarios']:
        row=s['components'][0];used=row['properties_used']
        expected=58*used['vs_fraction_wet']['range']['low']*used['bmp_ml_g_vs']['range']['low']/1000
        assert s['methane_m3']==pytest.approx({'low':expected,'high':expected})
        assert s['engineering']['complete_charge_volume_l'] is None
        assert 'Unambiguous normal pressure' in row['source']['conditions']['gas_basis_missing'][0]

@pytest.mark.parametrize('kwargs',[{'allow_literature_transfer':False},{'components':[{'id':'c','material':'grass','quantity':58,'data_mode':'MEASURED'}]},{'components':[{'id':'c','material':'grass','quantity':58,'material_state':'dry'}]}])
def test_no_unjustified_grass_transfer(kwargs):
    assert scientific_request(request('grass',58,**kwargs))['scenarios'][0]['methane_m3'] is None

def test_water_does_not_increase_methane():
    a=scientific_request(request())['scenarios'][0]
    b=scientific_request(request(decision={'reactor':{'dilution_water_l':10}}))['scenarios'][0]
    assert a['methane_m3']==b['methane_m3']
    assert b['engineering']['feed_plus_water_ts_fraction']['low']==pytest.approx(5*.1264/15)

def test_partial_charge_detects_overfill_without_density_of_other_component():
    r=request(components=[{'id':'c1','material':'cattle_manure','quantity':80,'unit':'L'}, {'id':'c2','material':'grass','quantity':58}],
        reactor_total_volume_l=50,decision={'reactor':{'operating_mode':'batch'}})
    e=evaluate(r,mixing.evaluate(r))
    assert e['known_charge_volume_l']['low']==80
    assert e['status']=='PHYSICALLY_INFEASIBLE'
    assert e['complete_charge_volume_l'] is None

def test_range_upper_bound_is_not_certain_overfill():
    r=request(components=[{'id':'c','material':'other_organic','quantity':50,'properties':{'density_kg_l':{'low':.5,'high':1}}}],reactor_total_volume_l=80,decision={'reactor':{'operating_mode':'batch'}})
    e=evaluate(r,mixing.evaluate(r))
    assert not e['violations']
    assert 'possible_charge_exceeds_total_volume' in e['warnings']

def test_continuous_daily_feed_not_instantaneous_charge():
    r=request(components=[{'id':'c','material':'food_waste','quantity':200,'unit':'L'}],reactor_total_volume_l=100,decision={'reactor':{'operating_mode':'continuous'}})
    assert evaluate(r,mixing.evaluate(r))['status']!='PHYSICALLY_INFEASIBLE'

def test_chat_preserves_handoff_and_water():
    state=DialogueState(mixture_components=[{'id':'c','material':'food_waste','quantity':5}],advanced={'request_overrides':{'reactor_total_volume_l':90,'allow_literature_transfer':False}})
    s=analytical.scientific(analytical.context(state))
    assert s['reactor_total_volume_l']==90
    assert s['scenarios'][0]['methane_m3'] is None

def test_literal_costs_are_partial_not_zero_filled():
    r=decision_bridge.propose('Подготовка 100 тенге, транспорт 50 тенге, обслуживание 20 тенге.',DialogueState())
    assert sum(x['low'] for x in r['costs'].values())==170
    assert not r['all_operating_costs_included']
    assert 'storage' not in r['costs']

def test_calculation_intent_and_cattle_slurry_identity():
    parsed=nlu.extract('Смешай 4 кг коровьего навоза, 2 кг травы и 1 кг пищевых отходов. Рассчитай метан и энергию.',DialogueState())
    assert 'methane_yield' in parsed.intents
    assert catalog.matches('80 литров навозной жижи КРС')[0]['material']=='cattle_manure'

def test_unknown_profile_not_claimed_as_transferred():
    s=scientific_request(request('other_organic'))['scenarios'][0]
    assert s['result_level']=='UNAVAILABLE'
    assert not s['assumptions']

def test_explicit_dry_food_waste_does_not_inherit_prepared_pulp_profile():
    state=apply(DialogueState(),nlu.extract('У меня 5 кг сухих пищевых отходов. Сколько метана?'))
    assert state.value('physical_state')=='dry'
    assert state.value('material_state')=='dry'
    result=analytical.scientific(analytical.context(state))
    assert all(s['methane_m3'] is None for s in result['scenarios'])
    assert all('baek2020-food-pulp' not in s['profile_ids'] for s in result['scenarios'])

@pytest.mark.parametrize('text,quantity,unit',[
    ('Сколько метана из 500 граммов пищевых отходов?',500,'g'),
    ('Сколько метана из 0,1 тонны свиного навоза?',.1,'t'),
    ('Сколько метана из 8 литров свиного навоза?',8,'L')])
def test_feed_quantity_never_becomes_reported_methane(text,quantity,unit):
    facts={e.name:e.value for e in nlu.extract(text,DialogueState()).entities}
    assert facts['quantity']==quantity
    assert facts['unit']==unit
    assert 'reported_methane_volume_m3' not in facts
