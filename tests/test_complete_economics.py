"""Independent SI/accounting assertions and a real-data 142 L end-to-end benchmark."""
import main
import copy,json,os,sqlite3,tempfile,unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
from fastapi.testclient import TestClient
from src.data.prepare import ROOT
from src.market.store import Store
from src.market.domain import market_today
from src.market.api import create_app
from src.estimation.schemas import EstimateRequest
from src.research.orchestrator import research_and_estimate
from src.economics.decision_schemas import DecisionInputs,ReactorInputs,GasBasis
from src.economics.energy_conversion import convert,pair
from src.economics.gas_composition import biogas_volume,compatible
from src.economics.reactor_balance import calculate
from src.economics.decision_engine import decide
from src.agent.conversation import ConversationAgent
from src.agent.providers import HybridLLM,ProviderError,JSONProvider
from src.agent.tools import ToolRegistry

def measured_inputs():
    basis={'temperature_k':273.2,'pressure_pa':101325,'moisture':'dry','description':'TEST documented gas basis'}
    def value(n):return {'low':n,'high':n,'provenance':'MEASURED','evidence':'TEST synthetic formula fixture, not real equipment'}
    def quote(value,commodity,unit):return {'value':value,'commodity':commodity,'unit':unit,'region':'KZ-Karaganda','published_at':market_today().isoformat(),'confirmed':True,'counterparty_confirmed':True,'source':'TEST quote only','consumer_class':'TEST household','tax_basis':'TEST tax basis','material_state':'slurry'}
    reactor={'reactor_working_volume_l':160,'headspace_l':40,'inoculum_volume_l':0,'dilution_water_l':0,'resident_liquid_volume_l':0,'operating_mode':'batch','reactor_type':'TEST single-charge vessel','engineering_review_confirmed':True,
             'temperature_c':35,'initial_temperature_c':15,'ambient_temperature_c':15,'heated_mass_kg':100,'heat_capacity_kj_kg_k':4,'heat_loss_coefficient_w_k':0,'duration_days':1,'heater_efficiency':1,'heating_carrier':'electricity','auxiliary_energy_kwh':1,'energy_scope':'entire_batch','provenance':'MEASURED'}
    return {'gas_use':'heat','gas_basis':copy.deepcopy(basis),'composition_basis':copy.deepcopy(basis),'methane_fraction':value(.6),'recovery_fraction':value(1),'thermal_efficiency':value(.8),'electrical_efficiency':value(.25),'chp_thermal_efficiency':value(.45),'chp_electrical_efficiency':value(.25),
            'use_reference_scenarios':False,'heating_value_kwh_m3':9.97,'heating_value_basis':basis,'equipment_evidence':'TEST specifications','reactor':reactor,
            'quotes':{'feedstock':quote(1,'cattle_manure','KZT/kg'),'electricity':quote(20,'electricity','KZT/kWh'),'heat':quote(10,'useful_heat','KZT/kWh')},'consumer_class':'TEST household','tax_basis':'TEST tax basis',
            'costs':{key:value(0) for key in ['preparation','maintenance','storage','transport','gas_cleaning','digestate_handling','packaging','sale_transport','sale_storage','sale_packaging']},'all_operating_costs_included':True,'heat_demand_kwh':1000,'electricity_demand_kwh':1000,'replacement_heat_source':'priced_useful_heat'}

class CompleteEconomicsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.store=Store(Path(self.tmp.name)/'isolated.sqlite3')
        self.env=patch.dict(os.environ,{'BIOREACTOR_RESEARCH_ONLINE':'0'});self.env.start();self.addCleanup(self.env.stop)
    def measured(self,settings=None):
        return research_and_estimate(self.store,EstimateRequest(material='cattle_manure',material_state='slurry',volume_l=100,mass_kg=100,vs_mass_kg=10,bmp_ml_g_vs=300,gas_reference='TEST dry gas',reactor_total_volume_l=200,region_confirmed=True,decision=settings or measured_inputs()))
    def row(self,r,kind):return next(x for x in r['decision_analysis']['scenarios'] if x['id']==kind)
    def test_biogas_independent_formula(self):self.assertEqual(biogas_volume(pair(3),pair(.6)),pair(5))
    def test_biogas_fraction_bounds_and_invalid(self):
        self.assertEqual(biogas_volume({'low':3,'high':4},{'low':.5,'high':.8}),{'low':3.75,'high':8})
        for fraction in [pair(0),pair(1.1),pair(-.1)]:
            with self.assertRaises(ValueError):biogas_volume(pair(3),fraction)
    def test_fuel_heat_electricity_independent_formulas(self):
        r=convert(pair(2),10,pair(.5),pair(.8),pair(.25),pair(.45),pair(.25))
        self.assertEqual(r['potential_fuel_kwh'],pair(20));self.assertEqual(r['recovered_fuel_kwh'],pair(10))
        self.assertEqual(r['heat_only_kwh'],pair(8));self.assertEqual(r['electricity_only_kwh'],pair(2.5))
    def test_chp_one_fuel_stream_balance(self):
        r=convert(pair(2),10,pair(1),pair(.8),pair(.25),pair(.45),pair(.25))
        self.assertAlmostEqual(r['chp_heat_kwh']['low']+r['chp_electricity_kwh']['low']+r['chp_unconverted_fuel_kwh']['low'],20)
    def test_efficiency_and_recovery_rejected(self):
        for setting in [{'thermal_efficiency':pair(1.01)},{'recovery_fraction':pair(-.01)},{'methane_fraction':pair(0)},{'chp_thermal_efficiency':pair(.7),'chp_electrical_efficiency':pair(.5)}]:
            with self.subTest(setting=setting),self.assertRaises(ValueError):DecisionInputs.model_validate(setting)
    def test_zero_negative_and_boolean_volume_rejected(self):
        for v in [0,-1,True]:
            with self.assertRaises(ValueError):EstimateRequest(volume_l=v)
    def test_missing_basis_does_not_convert_actual_gas(self):
        s=measured_inputs();s.pop('gas_basis');s.pop('composition_basis');s.pop('heating_value_basis')
        r=self.measured(s)['decision_analysis'];self.assertEqual(r['energy']['outputs'],{});self.assertIsNone(r['biogas']['potential_biogas_m3'])
    def test_wet_dry_and_reference_mismatch(self):
        dry=GasBasis(temperature_k=273.2,pressure_pa=101325,moisture='dry')
        for other in [GasBasis(temperature_k=300,pressure_pa=101325,moisture='dry'),GasBasis(temperature_k=273.2,pressure_pa=101325,moisture='wet')]:self.assertFalse(compatible(dry,other,True)[0])
        s=measured_inputs();s['composition_basis']['temperature_k']=300
        self.assertIsNone(self.measured(s)['decision_analysis']['biogas']['potential_biogas_m3'])
    def test_initial_heating_loss_and_named_loads(self):
        p=ReactorInputs(temperature_c=35,initial_temperature_c=15,ambient_temperature_c=10,heated_mass_kg=100,heat_capacity_kj_kg_k=4,u_w_m2_k=2,area_m2=3,duration_days=2,heater_efficiency=.8,heating_carrier='electricity',energy_scope='entire_batch',loads_complete=True,loads=[{'name':'TEST mixer','power_w':10,'hours':48,'duty_fraction':.5},{'name':'TEST electronics','power_w':1,'hours':48}])
        r=calculate(p);self.assertAlmostEqual(r['initial_heating_kwh'],100*4*20/3600/.8)
        self.assertAlmostEqual(r['maintenance_heating_kwh'],2*3*25*48/1000/.8)
        self.assertAlmostEqual(r['auxiliary_kwh'],.288)
        self.assertAlmostEqual(r['total_energy_kwh'],100*4*20/3600/.8+2*3*25*48/1000/.8+.288)
    def test_ua_and_named_load_conflicts(self):
        with self.assertRaises(ValueError):ReactorInputs(heat_loss_coefficient_w_k=3,u_w_m2_k=1,area_m2=1)
        with self.assertRaises(ValueError):calculate(ReactorInputs(auxiliary_energy_kwh=10,loads_complete=True,loads=[{'name':'TEST','power_w':1,'hours':1}]))
    def test_unknown_reactor_temperature_not_37(self):
        r=research_and_estimate(self.store,EstimateRequest(volume_l=142,material_state='slurry'))['decision_analysis']
        self.assertIsNone(r['reactor_balance']['initial_heating_kwh']);self.assertIsNone(r['reactor_balance']['total_energy_kwh'])
        self.assertTrue(all(x['inputs']['temperature_c']!=37 for x in r['illustrative_reactor_energy_cases']))
    def test_heat_net_profit_and_independent_cost_formula(self):
        r=self.measured();row=self.row(r,'B_heat')
        expected=(3*9.97*.8)*10-(100*4*20/3600+1)*20
        self.assertAlmostEqual(row['net_result_kzt']['low'],expected)
        self.assertEqual(r['decision_analysis']['decision']['status'],'PROCESSING_PREFERRED')
    def test_electric_internal_use_counted_once(self):
        s=measured_inputs();s['gas_use']='electricity';r=self.measured(s)
        expected=(3*9.97*.25-(100*4*20/3600+1))*20
        self.assertAlmostEqual(self.row(r,'C_electricity')['net_result_kzt']['low'],expected)
        self.assertEqual(r['decision_analysis']['decision']['status'],'SELLING_PREFERRED')
    def test_electric_price_break_even_accounts_for_internal_loads(self):
        r=self.measured();row=self.row(r,'C_electricity')
        self.assertAlmostEqual(row['break_even']['minimum_product_price']['low'],100/(3*9.97*.25-(100*4*20/3600+1)))
    def test_chp_joint_benefit_not_heat_only_plus_electric_only(self):
        r=self.measured();row=self.row(r,'CHP')
        expected=3*9.97*.45*10+(3*9.97*.25-(100*4*20/3600+1))*20
        self.assertAlmostEqual(row['net_result_kzt']['low'],expected)
    def test_capital_allocated_to_processing_not_sale(self):
        s=measured_inputs();s.update(include_capital=True,capital_cost_per_batch=pair(50));r=self.measured(s)
        self.assertEqual(self.row(r,'A_sell_feedstock')['net_result_kzt'],pair(100))
        self.assertAlmostEqual(self.row(r,'B_heat')['net_result_kzt']['low'],(3*9.97*.8)*10-(100*4*20/3600+1)*20-50)
    def test_missing_operating_cost_not_zero(self):
        s=measured_inputs();s['costs'].pop('maintenance');r=self.measured(s)
        self.assertIsNone(self.row(r,'B_heat')['net_result_kzt']);self.assertIsNotNone(self.row(r,'B_heat')['break_even']['maximum_total_processing_cost_to_match_sale_kzt'])
    def test_stale_future_missing_and_wrong_region_tariffs(self):
        for update in [{'published_at':'2020-01-01'},{'published_at':None},{'region':'KZ-Almaty'},{'commodity':'natural_gas','unit':'KZT/m3'}]:
            s=measured_inputs();s['quotes']['electricity'].update(update);a=self.measured(s)['decision_analysis']
            self.assertEqual(a['prices']['electricity']['status'],'unusable');self.assertFalse(any(x.get('evidence_confirmed') for x in a['scenarios'] if x['id']=='C_electricity'))
    def test_missing_tariff_no_savings(self):
        s=measured_inputs();s['quotes'].pop('electricity');r=self.measured(s)
        self.assertIsNone(self.row(r,'C_electricity')['gross_benefit_reference_kzt'])
    def test_unconfirmed_feedstock_not_guaranteed_net_proceeds(self):
        s=measured_inputs();s['quotes']['feedstock']['counterparty_confirmed']=False
        r=self.measured(s);self.assertIsNone(self.row(r,'A_sell_feedstock')['net_result_kzt'])
        self.assertTrue(r['decision_analysis']['decision']['status'].startswith('CONDITIONALLY'))
    def test_minimum_order_and_state_comparability(self):
        for change in [{'minimum_batch_kg':1000},{'material_state':'compost'}]:
            s=measured_inputs();s['quotes']['feedstock'].update(change)
            self.assertIsNone(self.row(self.measured(s),'A_sell_feedstock')['confirmed_buyer_gross_offer_kzt'])
    def test_high_heating_and_low_recovery_favour_sale_conditionally(self):
        for change in ['heat','recovery']:
            s=measured_inputs()
            if change=='heat':s['reactor']['heat_loss_coefficient_w_k']=100
            else:s['recovery_fraction']=pair(.05)
            r=self.measured(s);self.assertIn('SELLING_PREFERRED',r['decision_analysis']['decision']['status'])
    def test_unknown_and_insufficient_working_volume(self):
        s=measured_inputs();s['reactor'].pop('reactor_working_volume_l');r=self.measured(s)
        self.assertEqual(r['decision_analysis']['decision']['status'],'CONDITIONALLY_PROCESSING_PREFERRED')
        s['reactor']['reactor_working_volume_l']=80;r=self.measured(s)
        self.assertEqual(r['decision_analysis']['decision']['status'],'PHYSICALLY_INFEASIBLE')
    def test_safety_review_deterministic(self):
        s=measured_inputs();s['reactor']['safety_review_required']=True
        self.assertEqual(self.measured(s)['decision_analysis']['decision']['status'],'REQUIRES_SAFETY_REVIEW')
    def test_no_fictitious_gas_or_digestate_income(self):
        r=self.measured();self.assertIsNone(self.row(r,'D_sell_gas')['revenue_kzt']);self.assertIsNone(self.row(r,'E_digestate')['revenue_kzt'])
    def test_natural_gas_quote_cannot_sell_raw_biogas(self):
        s=measured_inputs();s.update(gas_sale_technical_confirmed=True,gas_sale_legal_confirmed=True,gas_quality_confirmed=True,gas_storage_transport_confirmed=True)
        s['quotes']['gas_sale']={**s['quotes']['electricity'],'commodity':'natural_gas','unit':'KZT/m3','gas_basis':s['gas_basis']}
        self.assertIsNone(self.row(self.measured(s),'D_sell_gas')['revenue_kzt'])
    def test_explicit_eligible_gas_and_digestate_quotes_are_calculated(self):
        s=measured_inputs();s.update(gas_use='sell_gas',gas_sale_technical_confirmed=True,gas_sale_legal_confirmed=True,gas_quality_confirmed=True,gas_storage_transport_confirmed=True,digestate_mass_kg=90,digestate_quality_confirmed=True,digestate_market_allowed=True)
        s['quotes']['gas_sale']={**s['quotes']['feedstock'],'value':100,'commodity':'raw_biogas','unit':'KZT/m3','gas_basis':s['gas_basis']}
        s['quotes']['digestate']={**s['quotes']['feedstock'],'value':1,'commodity':'digestate','unit':'KZT/kg'}
        s['costs']['gas_sale_transport']=pair(0);s['costs']['digestate_transport']=pair(0)
        r=self.measured(s);cost=(100*4*20/3600+1)*20
        self.assertEqual(self.row(r,'D_sell_gas')['revenue_kzt'],pair(500));self.assertAlmostEqual(self.row(r,'D_sell_gas')['net_result_kzt']['low'],500-cost)
        self.assertAlmostEqual(self.row(r,'D_sell_gas')['break_even']['minimum_product_price']['low'],(100+cost)/5)
        self.assertAlmostEqual(self.row(r,'E_digestate')['net_result_kzt']['low'],90-cost)
    def test_unknown_external_heat_price_not_zero_for_recovery_threshold(self):
        s=measured_inputs();s['reactor']['heating_carrier']='external_heat';s['quotes'].pop('heat')
        row=self.row(self.measured(s),'C_electricity');self.assertIsNone(row['net_result_kzt']);self.assertNotIn('minimum_recovery_fraction_sensitivity',row['break_even'])
    def test_partial_heated_mass_does_not_price_entire_feedstock(self):
        s=measured_inputs();s['reactor']['heated_mass_kg']=50;r=self.measured(s)
        self.assertFalse(r['decision_analysis']['reactor_balance']['mass_scope_consistent']);self.assertIsNone(self.row(r,'B_heat')['net_result_kzt'])
    def test_overlap_is_conditional(self):
        f={'status':'GEOMETRICALLY_CONSISTENT','engineering_review_confirmed':True}
        rows=[{'id':'A_sell_feedstock','net_result_kzt':pair(100),'evidence_confirmed':True},{'id':'B_heat','net_result_kzt':{'low':50,'high':200},'evidence_confirmed':True}]
        self.assertEqual(decide(f,rows,'heat',True)['status'],'CONDITIONALLY_PROCESSING_PREFERRED')
    def test_known_loss_against_reference_sale_is_not_processing_preferred(self):
        f={'status':'UNKNOWN','engineering_review_confirmed':False}
        rows=[{'id':'A_sell_feedstock','net_result_kzt':None,'reference_asking_value_kzt':pair(100),'evidence_confirmed':False},{'id':'B_heat','net_result_kzt':pair(-50),'evidence_confirmed':False}]
        self.assertEqual(decide(f,rows,'heat',True)['status'],'CONDITIONALLY_SELLING_PREFERRED')
    def test_reference_benchmark_142_l_real_preserved_prices(self):
        baseline=ROOT/'reports/stage7_5/pre_stage7_5.sqlite3'
        with closing(sqlite3.connect(baseline)) as source,closing(sqlite3.connect(self.store.path)) as target:source.backup(target)
        r=research_and_estimate(self.store,EstimateRequest(volume_l=142,material_state='slurry',reactor_total_volume_l=200))
        a=r['decision_analysis'];self.assertAlmostEqual(r['wet_mass_kg']['low'],143.846);self.assertAlmostEqual(r['vs_mass_kg']['low'],14.6147536)
        self.assertAlmostEqual(r['methane_potential_m3']['low'],2.92295072);self.assertAlmostEqual(r['methane_potential_m3']['high'],4.1139956)
        self.assertEqual(r['result_level'],'LITERATURE_ESTIMATE');self.assertAlmostEqual(a['biogas']['potential_biogas_m3']['low'],2.92295072/.6)
        self.assertAlmostEqual(a['energy']['outputs']['heat_only_kwh']['low'],2.92295072*9.97*.6*.8)
        self.assertAlmostEqual(a['energy']['outputs']['electricity_only_kwh']['high'],4.1139956*9.97*.8*.25)
        self.assertIsNone(a['reactor_balance']['total_energy_kwh']);self.assertIsNone(self.row(r,'D_sell_gas')['revenue_kzt'])
        self.assertEqual(a['decision']['status'],'CONDITIONALLY_PROCESSING_PREFERRED');self.assertIsNotNone(self.row(r,'B_heat')['break_even']['maximum_total_processing_cost_to_match_sale_kzt'])
    def test_multiturn_compact_followup_usage_change_and_memory(self):
        agent=ConversationAgent(llm=HybridLLM(providers=[]),registry=ToolRegistry(self.store),research_enabled=True)
        first=agent.ask('У меня 142 литра коровьего навоза и реактор 200 литров. Сколько биогаза?')
        second=agent.ask('Навозная жижа');third=agent.ask('Для отопления');fourth=agent.ask('Для электричества')
        # A resolved form enables a concise numerical answer; it is naturally
        # longer than the initial clarification question.
        self.assertLess(len(second['answer']),400);self.assertIn('2.92',second['answer']);self.assertNotIn('таблица 1',second['answer'])
        # v7.7 does not ask for gas use when the user requested only gas yield.
        self.assertIsNone(second['pending_question']);self.assertEqual(agent.state.value('quantity'),142);self.assertEqual(agent.state.value('reactor_total_volume_l'),200)
        self.assertEqual(agent.state.decision_settings['gas_use'],'electricity');self.assertIsNone(agent.state.value('thermal_efficiency'))
    def test_structured_inputs_accepted_and_invalid_efficiency_preserves_state(self):
        a=ConversationAgent(llm=HybridLLM(providers=[]),registry=ToolRegistry(self.store),research_enabled=True)
        a.ask('У меня 142 литра коровьего навоза. Сколько биогаза?')
        r=a.ask(json.dumps({'decision_inputs':{'thermal_efficiency':pair(.8),'reactor':{'temperature_c':35}}}))
        self.assertTrue(r['context_updated']);self.assertEqual(a.state.decision_settings['reactor']['temperature_c'],35)
        r=a.ask(json.dumps({'decision_inputs':{'thermal_efficiency':pair(1.5)}}));self.assertFalse(r['context_updated']);self.assertEqual(a.state.decision_settings['thermal_efficiency']['low'],.8)
    def test_legacy_fractions_and_efficiency_update_without_changing_purpose(self):
        a=ConversationAgent(llm=HybridLLM(providers=[]),registry=ToolRegistry(self.store),research_enabled=True)
        a.ask('У меня 142 литра коровьего навоза. Сколько биогаза?');a.ask('Для отопления')
        r=a.ask('Допустим электрический КПД 30%')
        self.assertEqual(a.state.decision_settings['gas_use'],'heat');self.assertEqual(a.state.decision_settings['electrical_efficiency']['low'],.3)
        r=a.ask(json.dumps({'recovery_fraction':.9}));self.assertEqual(r['technical_metadata']['research_result']['decision_analysis']['energy']['parameters']['recovery_fraction']['low'],.9)
    def test_ru_kk_en_conversation(self):
        for first,second,language in [('I have 142 litres of cattle manure and a 200 litre reactor. How much biogas?','Cattle slurry','en'),('Менде 142 литр сиыр көңі және 200 литр реактор бар. Қанша биогаз?','Сұйық көң','kk')]:
            agent=ConversationAgent(llm=HybridLLM(providers=[]),registry=ToolRegistry(self.store),research_enabled=True)
            agent.ask(first);r=agent.ask(second);self.assertEqual(r['memory']['language'],language);self.assertEqual(agent.state.value('material_state'),'slurry');self.assertIn('2.92',r['answer'])
    def test_real_fastapi_compatibility_and_new_decision_route(self):
        with TestClient(create_app(self.store,scheduler_enabled=False)) as client:
            body={'volume_l':142,'material_state':'slurry','reactor_total_volume_l':200}
            old=client.post('/api/research/estimate',json=body);new=client.post('/api/research/decision',json=body)
            self.assertEqual(new.status_code,200);self.assertEqual(old.json()['methane_potential_m3'],new.json()['methane_potential_m3']);self.assertEqual(new.json()['decision_analysis']['version'],'7.5')
            self.assertEqual(client.post('/api/research/decision',json={**body,'decision':{'thermal_efficiency':pair(1.5)}}).status_code,422)

if __name__=='__main__':unittest.main()
