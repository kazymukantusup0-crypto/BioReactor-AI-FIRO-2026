"""v8 scientific and task-completion contracts; TEST ONLY fixtures, no fake data."""
import main,copy,json
import pytest
from src.agent.conversation import ConversationAgent
from src.agent.providers import HybridLLM
from src.agent.tools import ToolRegistry
from src.market.store import Store
from src.advisor.schemas import Component,AdvisorRequest,ComparisonRequest
from src.advisor.conversion import convert,density_for
from src.advisor.mixing import evaluate
from src.advisor.advanced_science import prepared
from src.advisor.catalog import choose

MAIN='У меня 156 литров навоза с подстилкой и реактор на 200 литров. Рассчитай биогаз, тепло, электричество, затраты и выгоду'
@pytest.fixture
def agent(tmp_path):return ConversationAgent(research_enabled=True,llm=HybridLLM(providers=[]),registry=ToolRegistry(Store(tmp_path/'test.sqlite3')))
def c(**kw):return Component(id='c1',material='cattle_manure',quantity=156,unit='L',**kw)

def test_pending_species_resumes_every_original_goal_after_sqlite_serialization(agent):
    first=agent.ask(MAIN);assert first['pending_question']['id']=='advanced-species';assert not first['tools']
    restored=ConversationAgent(state=json.loads(agent.state.model_dump_json()),registry=agent.registry,llm=HybridLLM(providers=[]))
    r=restored.ask('Коровий');assert r['pending_question'] is None;assert set(r['memory']['advanced']['task']['goals'])=={'gas','heat','electricity','economics'}
    assert {t['tool'] for t in r['tools']}=={'estimate_advanced_gas','estimate_advanced_energy','evaluate_advanced_economics'}
    assert 'Что рассчитать' not in r['answer'];assert 'кВт·ч' in r['answer'];assert 'Чистая выгода' in r['answer']

def test_main_chain_arithmetic_and_no_slurry_substitution(agent):
    r=agent.ask(MAIN.replace('навоза','коровьего навоза'));gas=r['technical_metadata']['results']['gas'];m=gas['mixture'];row=m['components'][0]
    assert row['material_state']=='bedded';assert 'oliveira' not in (row['profile_id'] or '')
    assert m['total_wet_mass_kg']['low']==pytest.approx(110.76)
    assert m['additive_methane_reference_m3']['low']==pytest.approx(110.76*.2353*.1092*273.2/273.15)
    assert gas['scenario_assumptions'];assert m['result_level']=='HYPOTHETICAL_SCENARIO'
    assert 'опилочной' in r['answer'];assert 'MAE' not in r['answer'];assert not r['actuator_access']

def test_dry_and_fresh_are_independent_and_dry_density_is_unknown(agent):
    agent.ask('У меня 50 кг сухого коровьего навоза');r=agent.ask('А если он свежий?');row=r['memory']['advanced']['scenario'][0]
    assert row['physical_state']=='dry';assert row['decay_state']=='fresh';assert row['material_state']=='dry'
    assert r['memory']['advanced']['inventory'][0]['decay_state']=='unknown'
    r=agent.ask('Переведи всё в литры');assert 'объём неизвестен' in r['answer'];assert '50.0 L' not in r['answer']

def test_quantity_then_straw_continues_same_scenario_without_promoting_inventory(agent):
    agent.ask(MAIN);agent.ask('Коровий');r=agent.ask('А если 200 литров?')
    assert r['memory']['advanced']['inventory'][0]['quantity']==156;assert r['memory']['advanced']['scenario'][0]['quantity']==200
    assert 'места нет' in r['answer']
    r=agent.ask('А если добавить 20 кг соломы?');assert len(r['memory']['advanced']['scenario'])==2;assert len(r['memory']['advanced']['inventory'])==1
    assert r['memory']['advanced']['scenario'][0]['material_state']=='bedded'

def test_mixed_followup_conversion_does_not_lose_pending_calculations(agent):
    agent.ask('У меня 50 кг сухого коровьего навоза');r=agent.ask('Добавь 20 кг пищевых отходов');assert len(r['memory']['advanced']['inventory'])==2
    r=agent.ask('Переведи всё в литры');assert len(r['technical_metadata']['results']['conversion']['conversions'])==2
    assert not any(x['tool']=='evaluate_advanced_economics' for x in r['tools'])

def test_format_is_short_and_does_not_recompute(agent):
    agent.ask(MAIN.replace('навоза','коровьего навоза'));r=agent.ask('Объясни простыми словами');assert not r['tools'];assert len(r['answer'])<800
    r=agent.ask('Ответь одним предложением');assert not r['tools'];assert len(r['answer'])<400
    r=agent.ask('Почему ты использовал такую плотность?');assert '0.710' in r['answer'];assert 'измерение вашей партии' in r['answer'];assert not r['tools']

def test_condition_cache_and_tool_selection(agent):
    agent.ask(MAIN);agent.ask('Коровий');a=agent.ask('Какая температура лучше?');b=agent.ask('Какая температура лучше?')
    assert [t['tool'] for t in a['tools']]==['get_matched_substrate_conditions'];assert b['tools'][0]['cache_hit']
    assert '35' in b['answer'];assert '50' not in b['answer'];assert 'оптимум' in b['answer']

def test_new_batch_isolated_from_vessel_and_pending_task(agent):
    agent.ask(MAIN);r=agent.ask('Новая партия: у меня 10 кг сухого коровьего навоза')
    assert r['memory']['advanced']['inventory'][0]['quantity']==10;assert not r['memory']['advanced']['reactor'];assert r['pending_question'] is None;assert r['memory']['advanced']['task']['goals']==['gas']

def test_unfinished_economics_is_retained_while_answering_temperature(agent):
    agent.ask(MAIN);agent.ask('Коровий');r=agent.ask('Какая температура лучше?')
    assert any('economics' in t['goals'] for t in r['memory']['advanced']['unfinished_tasks'])

def test_structured_inventory_update_retains_advanced_tasks(agent):
    agent.ask(MAIN);agent.ask('Коровий');r=agent.ask(json.dumps({'mixture_components':[{'id':'c1','material':'cattle_manure','quantity':10,'unit':'kg','physical_state':'dry','decay_state':'fresh'}]}))
    assert r['memory']['advanced']['inventory'][0]['quantity']==10;assert r['memory']['advanced']['task']['goals']==['gas','heat','electricity','economics'];assert r['context_updated']

def test_new_batch_clears_structured_vessel_overrides_and_empty_reset(agent):
    agent.ask(MAIN);agent.ask('Коровий');agent.ask(json.dumps({'mixture_components':[{'id':'c1','material':'cattle_manure','quantity':10,'unit':'L','physical_state':'bedded'}],'advisor_inputs':{'reactor_total_volume_l':200}}))
    r=agent.ask('Новая партия');assert r['memory']['advanced']['inventory']==[];assert not r['memory']['advanced'].get('request_overrides');assert '200' not in r['answer']

def test_two_simultaneous_components_do_not_share_material_axes(agent):
    r=agent.ask('У меня 50 кг сухого коровьего навоза и 20 кг пищевых отходов. Рассчитай газ')
    assert r['context_updated'];rows=r['memory']['advanced']['inventory'];assert rows[0]['physical_state']=='dry';assert rows[1]['animal']=='unknown';assert rows[1]['physical_state']=='unknown'

def test_density_illustration_is_not_recorded_as_measured(agent):
    agent.ask('У меня 50 кг сухого коровьего навоза');r=agent.ask('Допустим плотность 0.5 кг/л. Переведи в литры')
    cv=r['technical_metadata']['results']['conversion']['conversions'][0];assert cv['value']['low']==100;assert cv['density']['mode']=='ILLUSTRATIVE_ASSUMPTION'

def test_energy_parameter_change_uses_cached_methane(agent):
    agent.ask(MAIN);agent.ask('Коровий');r=agent.ask('Электрический КПД 30%')
    assert next(t for t in r['tools'] if t['tool']=='estimate_advanced_gas')['cache_hit'];assert not next(t for t in r['tools'] if t['tool']=='estimate_advanced_energy')['cache_hit'];assert '30%' in r['answer']

def test_millilitre_target_and_inventory_removal(agent):
    agent.ask('У меня 2 литра коровьего навоза с подстилкой');r=agent.ask('Переведи в миллилитры');assert r['technical_metadata']['results']['conversion']['conversions'][0]['value']['low']==2000
    agent.ask('Добавь 20 кг пищевых отходов');r=agent.ask('Убери пищевые отходы');assert len(r['memory']['advanced']['inventory'])==1

@pytest.mark.parametrize('q,u,target,expected',[(1000,'g','kg',1),(1,'kg','g',1000),(.001,'t','kg',1),(1000,'mL','L',1),(1,'m3','L',1000),(1,'L','mL',1000)])
def test_si_conversion_without_density(q,u,target,expected):
    x=c(material_state='dry');x.quantity=q;x.unit=u
    r=convert(x,target);assert r['value']['low']==pytest.approx(expected);assert r['density'] is None

def test_density_modes_and_inverse_bounds():
    measured=c(properties={'density_kg_l':{'low':.6,'high':.8,'provenance':'MEASURED'}})
    assert convert(measured,'kg')['value']=={'low':93.6,'high':124.80000000000001};assert convert(measured,'kg')['density']['mode']=='MEASURED'
    measured.quantity=120;measured.unit='kg';assert convert(measured,'L')['value']=={'low':150,'high':200}
    illustrative=c(properties={'density_kg_l':{'low':.5,'high':.5,'provenance':'HYPOTHETICAL_SCENARIO','evidence':'TEST ONLY explicit density'}})
    assert convert(illustrative,'kg')['density']['mode']=='ILLUSTRATIVE_ASSUMPTION'
    assert convert(c(material_state='bedded'),'kg')['density']['mode']=='LITERATURE_ESTIMATE'

@pytest.mark.parametrize('decay',['stored','rotted','composted'])
def test_storage_decay_never_borrows_fresh_bmp(decay):
    x=c(material_state='bedded',decay_state=decay);assert choose(x,True)[0] is None
    req,notes=prepared(AdvisorRequest(components=[x]));assert evaluate(req)['additive_methane_reference_m3'] is None

def test_straw_bedding_does_not_silently_use_sawdust_profile():
    x=c(material_state='bedded',bedding='straw');assert choose(x,True)[0] is None
    req,notes=prepared(AdvisorRequest(components=[x],assume_common_dry_gas_basis=True));assert notes
    assert evaluate(req)['result_level']=='HYPOTHETICAL_SCENARIO'

def test_measured_only_mode_disables_all_literature_transfer():
    x=c(material_state='bedded',data_mode='MEASURED');assert convert(x,'kg')['value'] is None
    r,notes=prepared(AdvisorRequest(components=[x]));assert not notes;assert evaluate(r)['additive_methane_reference_m3'] is None

def test_animal_mismatch_and_invalid_units_are_rejected():
    with pytest.raises(ValueError):c(animal='horse')
    with pytest.raises(ValueError):Component(id='x',material='straw',quantity=-1,unit='kg')

def test_sheep_goat_axes_remain_distinct():
    for animal in ['sheep','goat']:
        x=Component(id='x',material='sheep_goat_manure',animal=animal,physical_state='solid',quantity=10,unit='kg');assert x.animal==animal;assert convert(x,'L')['value']['low']==pytest.approx(10/.497)

def test_pig_profile_is_primary_measured_vdi_not_fitted_vertex():
    x=Component(id='x',material='swine_manure',material_state='slurry',quantity=1,unit='kg');r=evaluate(AdvisorRequest(components=[x]));row=r['components'][0]
    assert row['profile_id']=='pham2013-pig-vdi';assert row['methane_reference_m3']['low']==pytest.approx(.02275*.20784)

def test_availability_cannot_change_decay_or_bedding():
    x=c(material_state='bedded');base=AdvisorRequest(components=[x]);y=x.model_copy(update={'decay_state':'fresh'})
    with pytest.raises(ValueError):ComparisonRequest(base=base,candidates=[{'label':'TEST ONLY','components':[y]}])
