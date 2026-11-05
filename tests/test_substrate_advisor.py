"""Scientific invariants. Numeric fixtures are TEST ONLY, not market or experimental data."""
import main
import copy,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from src.market.store import Store
from src.market.api import create_app
from src.advisor.schemas import AdvisorRequest,Component,ComparisonRequest
from src.advisor.mixing import evaluate
from src.advisor.service import analyze
from src.advisor.optimization import compare,suggestions
from src.advisor.catalog import get_catalog
from src.agent.conversation import ConversationAgent
from src.agent.providers import HybridLLM
from src.agent.tools import ToolRegistry
from src.agent.dialogue_types import DialogueState
from src.agent.mixture_parser import explicit_components
from src.research.advisor_pipeline import advance,discover,STAGES
from src.research.evidence_store import EvidenceStore

def component(material='cattle_manure',quantity=50,unit='kg',state='slurry',identifier='c1',properties=None):
    return {'id':identifier,'material':material,'quantity':quantity,'unit':unit,'material_state':state,'properties':properties or {}}
def test_properties(bmp=300,vs=.1,ts=.2):
    return {'ts_fraction':ts,'vs_fraction_wet':vs,'bmp_ml_g_vs':bmp,'gas_basis':{'temperature_k':273.2,'pressure_pa':101325,'moisture':'dry','description':'TEST ONLY reference'}}

class SubstrateAdvisorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.store=Store(Path(self.tmp.name)/'isolated.sqlite3')
        env=patch.dict(os.environ,{'BIOREACTOR_RESEARCH_ONLINE':'0'});env.start();self.addCleanup(env.stop)
    def agent(self,state=None):return ConversationAgent(llm=HybridLLM(providers=[]),registry=ToolRegistry(self.store),research_enabled=True,state=state)
    def run_analysis(self,components=None,**kwargs):return analyze(self.store,{'components':components or [component()],**kwargs})
    def test_catalog_counts_names_separately_from_approved_profiles(self):
        c=get_catalog();self.assertEqual(c['recognized_categories'],15);self.assertEqual(c['materials_with_approved_profiles'],['cattle_manure','food_waste','grass','horse_manure','poultry_manure','sheep_goat_manure','straw','swine_manure']);self.assertEqual(c['approved_profile_count'],18);self.assertEqual(c['complete_density_solids_bmp_profile_count'],1)
        self.assertEqual(next(m for m in c['materials'] if m['id']=='vegetable_waste')['support_level'],'PARTIAL')
    def test_actual_rm1_142_l_reference_and_no_operating_default(self):
        r=self.run_analysis([component(quantity=142,unit='L')],reactor_total_volume_l=200);m=r['mixture']
        self.assertAlmostEqual(m['total_wet_mass_kg']['low'],143.846);self.assertAlmostEqual(m['additive_methane_reference_m3']['low'],2.92295072);self.assertAlmostEqual(m['additive_methane_reference_m3']['high'],4.1139956)
        self.assertIsNone(r['temperature']['candidate']);self.assertIsNone(r['duration']['recommended_batch_duration_days']);self.assertIsNone(r['decision_analysis']['feasibility']['working_volume_l'])
    def test_bedded_manure_does_not_borrow_slurry_density(self):
        r=self.run_analysis([component(state='bedded',quantity=100,unit='L')]);m=r['mixture'];self.assertEqual(m['total_wet_mass_kg']['low'],71);self.assertAlmostEqual(m['additive_methane_reference_m3']['low'],71*.2353*.1092);self.assertEqual(m['result_level'],'HYPOTHETICAL_SCENARIO');self.assertEqual(m['components'][0]['properties_used']['density_kg_l']['source_id'],'alberta2005')
    def test_composted_manure_has_no_transferred_bmp(self):
        self.assertIsNone(self.run_analysis([component(state='compost')])['mixture']['additive_methane_reference_m3'])
    def test_food_profile_is_measured_point_not_regression_vertex(self):
        m=self.run_analysis([component('food_waste',20,state='prepared_pulp')])['mixture'];self.assertAlmostEqual(m['additive_methane_reference_m3']['low'],20*.1206*.5275);self.assertEqual(m['additive_methane_reference_m3']['low'],m['additive_methane_reference_m3']['high'])
    def test_no_fitted_pig_bmp_or_grass_mixture_bmp_substitution(self):
        pig=self.run_analysis([component('swine_manure')])['mixture']['components'][0];self.assertEqual(pig['profile_id'],'pham2013-pig-vdi');self.assertEqual(pig['properties_used']['bmp_ml_g_vs']['range']['low'],207.84)
        self.assertIsNone(self.run_analysis([component('grass')])['mixture']['additive_methane_reference_m3'])
    def test_100_litres_liquid_pig_manure_uses_pig_profile_and_scoped_density(self):
        result=self.run_analysis([component('swine_manure',100,'L','slurry')]);row=result['mixture']['components'][0]
        self.assertEqual(row['profile_id'],'pham2013-pig-vdi')
        self.assertEqual(row['wet_mass_kg'],{'low':100,'high':100})
        self.assertAlmostEqual(row['methane_reference_m3']['low'],.472836)
        self.assertEqual(row['properties_used']['density_kg_l']['source_id'],'alberta2005')
        self.assertTrue(any('Cross-study transfer' in value for value in row['assumptions']))
        self.assertEqual(result['temperature']['studies'][0]['temperatures_c'],[37])
    def test_dry_chicken_uses_high_solids_chicken_reference_not_layer_or_wet_profile(self):
        result=self.run_analysis([component('poultry_manure',50,'kg','dry')]);row=result['mixture']['components'][0]
        self.assertEqual(row['profile_id'],'eftaxias2024-poultry')
        self.assertEqual(row['properties_used']['ts_fraction']['range']['low'],.6925)
        self.assertNotEqual(row['profile_id'],'ramos2019-layers-HD-sample1')
        self.assertIsNone(row['volume_l'])
        self.assertTrue(any('не образец после специальной сушки' in value for value in row['assumptions']))
        self.assertEqual(result['temperature']['studies'][0]['temperatures_c'],[38])
        self.assertEqual(result['duration']['studies'][0]['days'],[20])
    def test_unknown_manure_state_does_not_select_first_species_profile(self):
        rows=[component('swine_manure',100,'L','unknown'),component('poultry_manure',20,'kg','unknown',identifier='c2')]
        mix=self.run_analysis(rows)['mixture']
        self.assertEqual([row['profile_id'] for row in mix['components']],[None,None])
        self.assertIsNone(mix['additive_methane_reference_m3'])
        self.assertTrue(all('bmp_ml_g_vs' in row['missing'] for row in mix['components']))
    def test_literature_transfer_can_be_disabled(self):
        self.assertIsNone(self.run_analysis(allow_literature_transfer=False)['mixture']['additive_methane_reference_m3'])
    def test_unit_conservation_g_kg_t_and_l_m3(self):
        values=[]
        for q,u in [(1000,'g'),(1,'kg'),(.001,'t')]:values.append(self.run_analysis([component(quantity=q,unit=u)])['mixture']['additive_methane_reference_m3'])
        self.assertEqual(values[0],values[1]);self.assertEqual(values[1],values[2])
        a=self.run_analysis([component(quantity=1000,unit='L')]);b=self.run_analysis([component(quantity=1,unit='m3')]);self.assertEqual(a['mixture']['total_wet_mass_kg'],b['mixture']['total_wet_mass_kg'])
    def test_mass_does_not_imply_liquid_volume(self):
        self.assertAlmostEqual(self.run_analysis()['mixture']['sum_separate_volumes_l']['low'],50/1.013)
        self.assertIsNone(self.run_analysis([component(state='dry')])['mixture']['sum_separate_volumes_l'])
    def test_unknown_portion_is_not_zero_or_lower_bound(self):
        r=self.run_analysis([component(),component('grass',10,identifier='c2')],assume_common_dry_gas_basis=True)['mixture'];self.assertIsNone(r['additive_methane_reference_m3']);self.assertIsNotNone(r['known_component_additive_subtotal_m3']);self.assertIsNone(r['total_vs_kg'])
    def test_additive_mass_balance_without_synergy(self):
        rows=[component(properties=test_properties(),quantity=10),component('food_waste',20,identifier='c2',properties=test_properties(200,.2,.3))]
        m=self.run_analysis(rows,allow_literature_transfer=False)['mixture'];self.assertAlmostEqual(m['additive_methane_reference_m3']['low'],1.1);self.assertEqual(m['total_wet_mass_kg']['low'],30);self.assertIsNone(m['synergy_factor']);self.assertIsNone(m['measured_mixture_bmp']);self.assertEqual(m['result_level'],'HYPOTHETICAL_SCENARIO')
    def test_missing_bmp_reference_does_not_pool_methane(self):
        p=test_properties();p.pop('gas_basis');r=self.run_analysis([component(properties=p)],allow_literature_transfer=False);self.assertIsNone(r['mixture']['additive_methane_reference_m3'])
    def test_incompatible_source_bases_require_explicit_scenario(self):
        rows=[component(),component('food_waste',20,state='prepared_pulp',identifier='c2')]
        self.assertIsNone(self.run_analysis(rows)['mixture']['additive_methane_reference_m3']);m=self.run_analysis(rows,assume_common_dry_gas_basis=True)['mixture'];self.assertIsNotNone(m['additive_methane_reference_m3']);self.assertTrue(m['normalization'])
    def test_known_wet_gas_is_not_silently_dried(self):
        p=test_properties();p['gas_basis']['moisture']='wet';r=self.run_analysis([component(properties=p)],allow_literature_transfer=False,assume_common_dry_gas_basis=True);self.assertIsNone(r['mixture']['additive_methane_reference_m3'])
    def test_measured_ts_blocks_borrowed_literature_vs(self):
        r=self.run_analysis([component(properties={'ts_fraction':.1})]);self.assertIsNone(r['mixture']['total_vs_kg']);self.assertIsNone(r['mixture']['additive_methane_reference_m3'])
    def test_cn_uses_carbon_nitrogen_masses_not_mean_of_ratios(self):
        a={'carbon_fraction_wet':.1,'nitrogen_fraction_wet':.01};b={'carbon_fraction_wet':.3,'nitrogen_fraction_wet':.01}
        m=self.run_analysis([component(quantity=10,properties=a),component('food_waste',30,identifier='c2',properties=b)])['mixture'];self.assertAlmostEqual(m['cn_mass_ratio']['low'],25);self.assertIsNone(m['mixture_ph'])
    def test_cn_without_elemental_measurements_is_unknown(self):
        self.assertIsNone(self.run_analysis([component(state='bedded'),component('food_waste',20,state='prepared_pulp',identifier='c2')])['mixture']['cn_mass_ratio'])
    def test_olr_continuous_requires_feed_period_and_working_volume(self):
        r=self.run_analysis([component(quantity=10,properties=test_properties())],allow_literature_transfer=False,feeding_period_days=2,decision={'reactor':{'reactor_working_volume_l':100,'operating_mode':'continuous'}});self.assertAlmostEqual(r['mixture']['olr_kg_vs_m3_day']['low'],5)
        r=self.run_analysis(feeding_period_days=2,decision={'reactor':{'reactor_working_volume_l':100,'operating_mode':'batch'}});self.assertIsNone(r['mixture']['olr_kg_vs_m3_day'])
    def test_hrt_requires_full_hydraulic_feed_declaration(self):
        args={'total_daily_liquid_feed_l':10,'decision':{'reactor':{'reactor_working_volume_l':100,'operating_mode':'continuous'}}}
        self.assertIsNone(self.run_analysis(**args)['duration']['estimated_hrt_from_declared_feed_days']);args['daily_feed_includes_all_liquid']=True;self.assertEqual(self.run_analysis(**args)['duration']['estimated_hrt_from_declared_feed_days']['low'],10)
    def test_temperature_not_a_function_of_quantity(self):
        a=self.run_analysis([component(quantity=20,unit='L')])['temperature'];b=self.run_analysis([component(quantity=500,unit='L')])['temperature'];self.assertEqual(a,b);self.assertIsNone(a['default_setpoint_c'])
    def test_extreme_ph_does_not_create_temperature_recommendation(self):
        self.assertIsNone(self.run_analysis(measured_ph=3,monitoring_confirmed=True,temperature_control_confirmed=True)['temperature']['candidate'])
    def test_mock_readings_and_actuators_remain_unavailable(self):
        r=self.run_analysis();self.assertFalse(r['reactor_monitoring']['measurements_used']);self.assertIsNone(r['reactor_monitoring']['readings']);self.assertFalse(r['actuator_access'])
    def test_quantity_binding_in_three_languages_excludes_reactor(self):
        for text in ['У меня 50 кг коровьего навоза, 20 кг пищевых отходов и 10 кг травы, реактор на 200 литров','I have 50 kg cattle manure, 20 kg food waste and 10 kg grass and a 200 litre reactor','Менде 50 кг сиыр көңі, 20 кг тағам қалдықтары және 10 кг шөп, 200 литр реактор бар']:
            c=explicit_components(text);self.assertEqual([x.quantity for x in c],[50,20,10]);self.assertEqual([x.material for x in c],['cattle_manure','food_waste','grass'])
    def test_requested_russian_material_phrases_keep_species_state_and_quantity(self):
        pig=explicit_components('У меня 100 литров жидкого свиного навоза. Сколько получится газа?')[0]
        dry=explicit_components('У меня 50 кг сухого куриного помёта. Какая температура лучше?')[0]
        blend=explicit_components('Смешай 40 кг коровьего навоза и 20 кг птичьего помёта.')
        self.assertEqual((pig.material,pig.material_state,pig.physical_state,pig.quantity,pig.unit),('swine_manure','slurry','liquid',100,'L'))
        self.assertEqual((dry.material,dry.material_state,dry.poultry_type,dry.quantity,dry.unit),('poultry_manure','dry','chicken',50,'kg'))
        self.assertEqual([(item.material,item.quantity) for item in blend],[('cattle_manure',40),('poultry_manure',20)])
    def test_mixture_edits_and_restored_state(self):
        agent=self.agent();agent.ask('У меня 50 кг коровьего навоза, 20 кг пищевых отходов и 10 кг травы. Что получится, если смешать?')
        self.assertEqual(len(agent.state.mixture_components),3);agent=self.agent(agent.state.model_dump(mode='json'))
        agent.ask('Добавь ещё 5 кг пищевых отходов');self.assertEqual(agent.state.mixture_components[1]['quantity'],25)
        agent.ask('Убери траву');self.assertEqual(len(agent.state.mixture_components),2)
        agent.ask('Замени 25 кг пищевых отходов на 15 кг');self.assertEqual(agent.state.mixture_components[1]['quantity'],15)
        self.assertIsNone(agent.state.value('quantity'));self.assertIsNone(agent.state.value('mass_kg'))
    def test_what_if_keeps_inventory_and_user_confirmed_quantity(self):
        a=self.agent();a.ask('У меня 100 литров коровьей навозной жижи. Какая температура?');before=copy.deepcopy(a.state.mixture_components)
        a.ask('Что изменится, если увеличить навоз вдвое?');self.assertEqual(a.state.mixture_components,before);self.assertEqual(a.state.value('quantity'),100);self.assertEqual(a.state.mixture_scenario_components[0]['quantity'],200)
    def test_invalid_edit_keeps_previous_inventory(self):
        a=self.agent();a.ask('У меня 50 кг коровьего навоза и 20 кг пищевых отходов');before=copy.deepcopy(a.state.mixture_components)
        for text in ['Добавь -5 кг пищевых отходов','Замени 20 кг пищевых отходов на 0 кг']:
            self.assertEqual(a.ask(text)['mode'],'input_rejected');self.assertEqual(a.state.mixture_components,before)
    def test_no_density_guess_for_volume_of_food(self):
        self.assertIsNone(self.run_analysis([component('food_waste',10,'L','prepared_pulp')])['mixture']['total_wet_mass_kg'])
    def test_generic_manure_has_separate_conditional_species_example(self):
        r=self.run_analysis([component('manure',142,'L')]);self.assertIsNone(r['mixture']['additive_methane_reference_m3']);self.assertAlmostEqual(r['conditional_reference_case']['mixture']['additive_methane_reference_m3']['low'],2.92295072)
    def test_total_biogas_is_conditional_and_methane_not_added_twice(self):
        r=self.agent().ask('У меня 142 литра навозной жижи и реактор на 200 литров. Сколько газа, какая температура и срок?')
        self.assertIn('4.87–7.48',r['answer']);self.assertIn('55–60 %',r['answer']);self.assertIn('Метан уже входит',r['answer'])
    def test_comparison_respects_availability_across_unit_conversions(self):
        base=AdvisorRequest(components=[component(quantity=1)])
        ok=ComparisonRequest(base=base,candidates=[{'label':'TEST','components':[component(quantity=1000,unit='g')]}]);self.assertIsNone(compare(self.store,ok)['preferred_mixture'])
        with self.assertRaises(ValueError):ComparisonRequest(base=base,candidates=[{'label':'TEST','components':[component(quantity=1001,unit='g')]}])
    def test_no_optimum_when_kinetics_stability_or_prices_missing(self):
        base=AdvisorRequest(components=[component(),component('food_waste',20,identifier='c2')]);r=compare(self.store,ComparisonRequest(base=base,candidates=suggestions(base)));self.assertIsNone(r['preferred_mixture']);self.assertTrue(all(c['objectives']['stability'] is None and c['objectives']['duration'] is None for c in r['candidates']))
    def test_comparison_cannot_change_component_property_evidence(self):
        base=AdvisorRequest(components=[component(properties=test_properties())])
        with self.assertRaises(ValueError):ComparisonRequest(base=base,candidates=[{'label':'TEST fabricated yield change','components':[component(properties=test_properties(900))]}])
    def test_material_names_can_precede_quantities(self):
        c=explicit_components('Коровий навоз: 50 кг, пищевые отходы: 20 кг, трава: 10 кг')
        self.assertEqual([(x.material,x.quantity) for x in c],[('cattle_manure',50),('food_waste',20),('grass',10)])
    def test_unknown_component_cannot_be_assigned_to_previous_material(self):
        with self.assertRaises(ValueError):explicit_components('У меня 50 кг коровьего навоза и 20 кг неизвестного материала')
    def test_dilution_water_and_density_are_not_wet_substrate_mass(self):
        c=explicit_components('50 кг коровьего навоза, 10 литров воды, плотность 1.013 кг/л, реактор 200 литров')
        self.assertEqual([(x.material,x.quantity) for x in c],[('cattle_manure',50)])
    def test_review_cannot_skip_stages_or_approve_llm_proposal(self):
        with self.assertRaises(ValueError):advance({'verification_stage':'DISCOVERED'},'APPROVED_FOR_ESTIMATION',{'reviewer':'TEST','evidence':'TEST'})
        with self.assertRaises(ValueError):advance({'verification_stage':'NUMERIC_DATA_VERIFIED'},'APPROVED_FOR_ESTIMATION',{'reviewer':'TEST LLM','evidence':'TEST','approved_scope':'TEST'})
    def test_full_review_requires_each_scoped_confirmation(self):
        record={'doi':'10.1234/TEST','title':'TEST ONLY','authors':['TEST'],'year':2020}
        for stage in STAGES[1:]:record=advance(record,stage,{'reviewer':'TEST manual reviewer','evidence':'TEST primary source','units_checked':True,'material_checked':True,'conditions_checked':True,'locator':'TEST table','approved_scope':'TEST ONLY','manual_review':True})
        self.assertEqual(record['verification_stage'],'APPROVED_FOR_ESTIMATION');self.assertEqual(len(record['reviews']),4)
    def test_discovery_metadata_never_approves_numeric_profiles(self):
        payload=json.dumps({'message':{'items':[{'DOI':'10.1234/TEST','title':['TEST ONLY metadata'],'author':[]}]}}).encode()
        with patch('src.research.advisor_pipeline.download',return_value=payload):r=discover(EvidenceStore(self.store),['grass'],['BMP'],True)
        self.assertEqual(r['discovered'][0]['verification_stage'],'DISCOVERED');self.assertFalse(r['discovered'][0]['numeric_use_allowed'])
    def test_new_tool_is_allowlisted_and_accepts_typed_inventory(self):
        r=ToolRegistry(self.store).execute('analyze_substrate_mixture',{'components':[component()]},{},'TEST');self.assertIn('mixture',r);self.assertNotEqual(r['status'],'error')
    def test_api_validation_and_append_only_advisor_history(self):
        with TestClient(create_app(self.store,scheduler_enabled=False)) as c:
            self.assertEqual(c.get('/api/advisor/catalog').status_code,200)
            for invalid in [0,-1,True]:self.assertEqual(c.post('/api/advisor/analyze',json={'components':[component(quantity=invalid)]}).status_code,422)
            self.assertEqual(c.post('/api/advisor/analyze',json={'components':[component()]}).status_code,200)
            self.assertEqual(len(c.get('/api/advisor/runs').json()['runs']),1)
    def test_conversion_save_restore_and_chat_handoff_api(self):
        components=[component('swine_manure',100,'L','slurry'),component('poultry_manure',20,'kg','dry','c2')]
        request={'components':components,'assume_common_dry_gas_basis':True}
        with TestClient(create_app(self.store,scheduler_enabled=False)) as client:
            converted=client.post('/api/advisor/convert',json={'request':{'components':[components[0]]},'target_unit':'kg'}).json()['conversions'][0]
            self.assertEqual(converted['status'],'ok');self.assertEqual(converted['value'],{'low':100,'high':100})
            saved=client.post('/api/advisor/mixtures',json={'name':'Pig and dry poultry','request':request,'display_units':{'c1':'L','c2':'kg'}})
            self.assertEqual(saved.status_code,201);data=saved.json()
            listed=client.get('/api/advisor/mixtures').json()['mixtures'][0]['request']
            loaded=client.get('/api/advisor/mixtures/'+data['mixture_id']).json()['request']
            self.assertEqual([row['quantity'] for row in listed['components']],[100,20])
            self.assertEqual([row['material_state'] for row in loaded['components']],['slurry','dry'])
            self.assertTrue(listed['assume_common_dry_gas_basis'])
            revision=client.post('/api/advisor/mixtures',json={'name':'Pig and dry poultry','mixture_id':data['mixture_id'],'request':request,'display_units':{'c1':'L','c2':'kg'}})
            self.assertEqual(revision.status_code,201);self.assertEqual(revision.json()['revision'],1)
            handoff=client.post('/api/advisor/handoff',json={'request':request,'mode':'no_llm'}).json()
            session=client.get('/api/dashboard/chat/sessions/'+handoff['session_id']).json()
            inventory=session['memory']['advanced']['inventory']
            self.assertEqual([(row['material'],row['quantity'],row['unit'],row['material_state']) for row in inventory],
                [('swine_manure',100,'L','slurry'),('poultry_manure',20,'kg','dry')])
            reply=client.post('/api/dashboard/chat/sessions/'+handoff['session_id']+'/messages',json={'message':'Оцени экономику этой смеси','request_id':'TEST_mixture_handoff'}).json()
            self.assertEqual(len(reply['memory']['mixture_components']),2)
            self.assertNotIn('HYPOTHETICAL_SCENARIO',reply['answer'])
    def test_human_answers_ru_kk_en_and_one_question(self):
        for message,lang in [('У меня 20 кг травы. Какая температура лучше?','ru'),('I have 20 kg grass. What temperature?','en'),('Менде 20 кг шөп бар. Қандай температура?','kk')]:
            r=self.agent().ask(message);self.assertEqual(r['memory']['language'],lang);self.assertLessEqual(r['answer'].count('?'),1);self.assertTrue(r['user_facing_answer']['paragraphs']);self.assertNotIn('HYPOTHETICAL_SCENARIO',r['answer'])

if __name__=='__main__':unittest.main()
