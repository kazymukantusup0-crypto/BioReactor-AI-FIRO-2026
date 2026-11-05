"""Scientific invariant tests. Every numerical record is a hypothetical TEST fixture."""
from pathlib import Path
import tempfile
import unittest
from src.market.store import Store
from src.optimizer.schemas import ProcessRequest, ProcessParameters
from src.optimizer.service import optimize
from src.optimizer.constraints import analyze_constraints, plan_batches
from src.optimizer.energy_model import estimate_energy
from src.optimizer.ranking import compare_results


def thermal(**changes):
    return dict(heated_mass_kg=10, heat_capacity_kj_kg_k=4, initial_temperature_c=20,
                temperature_c=35, ambient_temperature_c=20, heater_efficiency=.8,
                heat_loss_coefficient_w_k=2, duration_days=1, auxiliary_energy_kwh=.1,
                energy_scope='entire_feedstock', **changes)


def reactor():
    return dict(material='cattle_manure', feedstock_volume_l=800, reactor_total_volume_l=90,
                reactor_working_volume_l=65, operating_mode='batch', reactor_type='TEST vessel',
                inoculum_description='TEST user specified inoculum', gas_storage_conditions='TEST no operating approval',
                inoculum_volume_l=10, dilution_water_l=5, resident_liquid_volume_l=0,
                batch_duration_days=30, turnaround_days=1)


class OptimizerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.store = Store(Path(temp.name)/'TEST.sqlite3')

    def test_total_volume_does_not_assign_working_fraction(self):
        result = optimize(self.store, ProcessRequest(material='cattle_manure', feedstock_volume_l=800, reactor_total_volume_l=90))
        scenario = result['scenarios'][0]
        self.assertIsNone(scenario['input_parameters']['reactor_working_volume_l'])
        self.assertIsNone(scenario['predicted_outputs']['batch_plan']['batch_count'])
        self.assertEqual(scenario['feasibility_status'], 'INSUFFICIENT_DATA')
        self.assertIsNone(result['final_recommendation'])

    def test_impossible_working_volume_is_infeasible_not_clamped(self):
        p=ProcessParameters(reactor_total_volume_l=90,reactor_working_volume_l=95)
        self.assertEqual(analyze_constraints(p)['feasibility_status'],'INFEASIBLE')

    def test_occupancy_batch_count_and_calendar_from_explicit_values(self):
        plan=plan_batches(ProcessParameters(**reactor()))
        self.assertEqual(plan['feedstock_capacity_per_batch_l'],50)
        self.assertEqual(plan['batch_count'],16)
        self.assertEqual(plan['total_duration_days'],495)

    def test_cycle_unknown_retains_partial_plan_without_time_claim(self):
        data=reactor(); data.pop('batch_duration_days')
        plan=plan_batches(ProcessParameters(**data))
        self.assertEqual(plan['batch_count'],16)
        self.assertIsNone(plan['total_duration_days'])

    def test_continuous_hrt_is_not_batch_duration(self):
        p=ProcessParameters(operating_mode='continuous', reactor_working_volume_l=65,daily_feed_volume_l=5,daily_vs_mass_kg=.1)
        derived=analyze_constraints(p)['derived']
        self.assertEqual(derived['hydraulic_retention_days'],13)
        self.assertAlmostEqual(derived['olr_kg_vs_m3_day'],.1/.065)
        self.assertIsNone(plan_batches(p)['batch_count'])

    def test_missing_vs_refuses_precise_methane(self):
        request=ProcessRequest(material='cattle_manure',mass_kg=10,bmp_ml_ch4_g_vs=300,bmp_unit='mL CH4/g VS',bmp_provenance='scenario_assumption',bmp_evidence='TEST hypothesis',gas_volume_basis='TEST dry reference')
        methane=optimize(self.store,request)['scenarios'][0]['predicted_outputs']['methane']
        self.assertIsNone(methane['potential_methane_m3'])
        self.assertIn('vs_mass_kg',methane['missing'])

    def test_unsupported_material_has_no_model_bmp(self):
        methane=optimize(self.store,ProcessRequest(material='cattle_manure',vs_mass_kg=1,gas_volume_basis='TEST dry reference'))['scenarios'][0]['predicted_outputs']['methane']
        self.assertIsNone(methane['potential_methane_m3'])
        self.assertFalse(methane['model_result'].get('model_called'))

    def test_bmp_units_and_vs_to_potential_and_not_actual_yield(self):
        req=ProcessRequest(material='cattle_manure',mass_kg=10,ts_percent=10,vs_percent=80,vs_basis='TS',bmp_ml_ch4_g_vs=300,bmp_unit='mL CH4/g VS',bmp_provenance='scenario_assumption',bmp_evidence='TEST hypothetical BMP',gas_volume_basis='TEST dry reference',recovery_fraction=.5,methane_fraction=.6)
        methane=optimize(self.store,req)['scenarios'][0]['predicted_outputs']['methane']
        self.assertAlmostEqual(methane['potential_methane_m3'],.24)
        self.assertAlmostEqual(methane['recoverable_methane_scenario_m3'],.12)
        self.assertAlmostEqual(methane['raw_biogas_scenario_m3'],.2)
        self.assertNotIn('actual_yield_m3',methane)

    def test_energy_si_initial_maintenance_auxiliary(self):
        energy=estimate_energy(ProcessParameters(**thermal()))
        self.assertAlmostEqual(energy['initial_heating_kwh'],600/3600/.8)
        self.assertAlmostEqual(energy['maintenance_heating_kwh'],2*15*24/1000/.8)
        self.assertAlmostEqual(energy['total_energy_kwh'],600/3600/.8+.9+.1)

    def test_partial_energy_does_not_treat_unknown_heat_loss_as_zero(self):
        data=thermal();data.pop('heat_loss_coefficient_w_k')
        result=estimate_energy(ProcessParameters(**data))
        self.assertIsNotNone(result['initial_heating_kwh'])
        self.assertIsNone(result['total_energy_kwh'])

    def test_cooling_is_not_silently_zero_energy(self):
        data=thermal();data.update(initial_temperature_c=40)
        result=estimate_energy(ProcessParameters(**data))
        self.assertTrue(result['cooling_required'])
        self.assertIsNone(result['total_energy_kwh'])

    def test_invalid_physics_and_boolean_inputs_rejected(self):
        for inputs in [{'mass_kg':True},{'heater_efficiency':0},{'heater_efficiency':1.1},{'heat_loss_coefficient_w_k':-1},{'temperature_c':-274},{'user_limits':{'temperature_max_c':True}},{'mass_kg':float('nan')},{'material':' '}]:
            with self.subTest(inputs=inputs),self.assertRaises(ValueError):ProcessRequest(**inputs)

    def test_temperature_only_changes_energy_not_reference_bmp(self):
        data={**reactor(),**thermal(), 'mass_kg':10, 'vs_mass_kg':1,'bmp_ml_ch4_g_vs':300,'bmp_unit':'mL CH4/g VS','bmp_provenance':'scenario_assumption','bmp_evidence':'TEST assumed reference BMP','gas_volume_basis':'TEST dry reference',
            'candidates':[{'label':str(t),'overrides':{'temperature_c':t},'rationale':'TEST user temperature hypothesis'} for t in [35,38]]}
        result=optimize(self.store,ProcessRequest(**data))
        low,high=result['scenarios']
        self.assertEqual(low['predicted_outputs']['methane']['potential_methane_m3'],high['predicted_outputs']['methane']['potential_methane_m3'])
        self.assertGreater(high['predicted_outputs']['energy']['total_energy_kwh'],low['predicted_outputs']['energy']['total_energy_kwh'])

    def test_no_automatic_price_sensitivity_or_ranking_weights(self):
        result=optimize(self.store,ProcessRequest(material='cattle_manure'))
        self.assertEqual(result['sensitivity']['rows'],[])
        self.assertIsNone(result['comparison']['weights'])
        self.assertIsNone(result['comparison']['recommended_scenario_id'])

    def test_explicit_temperature_sensitivity_does_not_adjust_methane(self):
        data={**reactor(),**thermal(), 'vs_mass_kg':1,'bmp_ml_ch4_g_vs':300,'bmp_unit':'mL CH4/g VS','bmp_provenance':'scenario_assumption','bmp_evidence':'TEST reference assumption','gas_volume_basis':'TEST dry reference',
              'sensitivity':[{'parameter':'temperature_c','low':35,'high':38,'provenance':'USER_DEFINED_RANGE','evidence':'TEST chosen endpoints'}]}
        result=optimize(self.store,ProcessRequest(**data))['sensitivity']['rows'][0]
        self.assertEqual(result['outputs']['potential_methane_m3']['span'],0)
        self.assertGreater(result['outputs']['total_energy_kwh']['span'],0)

    def test_pareto_ranking_requires_explicit_complete_common_objectives(self):
        rows=[]
        for name,energy in [('a',1),('b',2)]:
            rows.append({'scenario_id':name,'label':name,'feasibility_status':'CONDITIONAL','input_parameters':{'material':'TEST','mass_kg':10,'energy_scope':'entire_feedstock'},'predicted_outputs':{'energy':{'total_energy_kwh':energy},'methane':{'potential_methane_m3':1}}})
        self.assertEqual(compare_results(rows,['energy','methane'])['pareto_fronts'],[['a'],['b']])
        self.assertEqual(compare_results(rows,['uncertainty'])['method'],'tradeoff_table')
        self.assertEqual(compare_results(rows,[])['method'],'tradeoff_table')
        rows[1]['input_parameters']['mass_kg']=20
        self.assertEqual(compare_results(rows,['energy'])['method'],'tradeoff_table')

    def test_new_material_does_not_inherit_old_measured_bmp_or_vs(self):
        req=ProcessRequest(material='cattle_manure',vs_mass_kg=1,bmp_ml_ch4_g_vs=300,bmp_unit='mL CH4/g VS',bmp_provenance='measured',bmp_evidence='TEST old material protocol',gas_volume_basis='TEST dry reference',candidates=[{'label':'New substrate','overrides':{'material':'swine_manure'},'rationale':'TEST changed material'}])
        methane=optimize(self.store,req)['scenarios'][0]['predicted_outputs']['methane']
        self.assertIsNone(methane['potential_methane_m3'])
        self.assertIsNone(methane['bmp_ml_ch4_g_vs'])

    def test_pretreatment_does_not_reuse_untreated_bmp(self):
        req=ProcessRequest(material='Whey',vs_mass_kg=1,bmp_ml_ch4_g_vs=300,bmp_unit='mL CH4/g VS',bmp_provenance='measured',bmp_evidence='TEST untreated reference',gas_volume_basis='TEST dry reference',candidates=[{'label':'Treatment','overrides':{'pretreatment':'TEST heat treatment'},'rationale':'TEST changed treatment'}])
        methane=optimize(self.store,req)['scenarios'][0]['predicted_outputs']['methane']
        self.assertIsNone(methane['potential_methane_m3'])

    def test_empty_market_has_no_profit_and_never_creates_prices(self):
        result=optimize(self.store,ProcessRequest(material='cattle_manure'))
        self.assertFalse(any(r.get('net_profit') is not None for r in result['scenarios'][0]['predicted_outputs']['economics'].get('scenarios',[])))
        with self.store.connect() as con:self.assertEqual(con.execute('SELECT COUNT(*) FROM observations').fetchone()[0],0)

    def test_market_adapter_preserves_a_to_d_ledgers_and_common_input_cost(self):
        from test_market import fixture,scenario_input
        from src.optimizer.economic_optimizer import evaluate_economics
        for ident,category in [('test_feed','organic_feedstock'),('test_power','electricity'),('test_gas','natural_gas'),('test_fert','organic_fertilizer')]:
            self.store.add_source(dict(id=ident,name='TEST fixture',url='https://example.invalid/TEST',category=category,adapter='manual'))
        self.store.import_prices([fixture(),fixture('electricity',10,'kWh','test_power'),fixture('raw_biogas',30,'m3','test_gas'),fixture('digestate',1,'kg','test_fert')])
        market=scenario_input();market.update(heating_cost=0,comparison_route='B')
        p=ProcessParameters(material='food_waste',mass_kg=20,energy_scope='entire_feedstock',market=market,feedstock_purchase_cost=40,capital_cost=1000,annual_batches=10,annual_fixed_cost=20)
        result=evaluate_economics(self.store,p,{'potential_methane_m3':10,'gas_volume_basis':'TEST_same_basis'},{'total_energy_kwh':2})
        rows={r['scenario']:r for r in result['scenarios']}
        self.assertTrue(all(r['status']=='ok' for r in rows.values()))
        self.assertAlmostEqual(rows['A']['net_profit'],-2)
        self.assertAlmostEqual(rows['B']['net_profit'],105)
        self.assertAlmostEqual(rows['C']['net_profit'],205)
        self.assertEqual(rows['B']['revenue'],200)  # no digestate/gas sales added to self-consumption
        self.assertAlmostEqual(result['payback']['simple_payback_years'],1000/1050)
        self.assertEqual(result['sensitivity'],[])

    def test_modeled_heating_cannot_be_charged_twice(self):
        from src.optimizer.economic_optimizer import evaluate_economics
        p=ProcessParameters(energy_scope='entire_feedstock',market={'heating_cost':10})
        result=evaluate_economics(self.store,p,{}, {'total_energy_kwh':2})
        self.assertEqual(result['status'],'needs_input')
        self.assertEqual(result['scenarios'],[])

    def test_unknown_user_cost_limit_cannot_be_ignored_for_energy_ranking(self):
        data={**reactor(),**thermal(),'objectives':['energy'],'user_limits':{'cost_max':100},
              'candidates':[{'label':str(t),'overrides':{'temperature_c':t},'rationale':'TEST explicit comparison'} for t in [35,38]]}
        result=optimize(self.store,ProcessRequest(**data))
        self.assertEqual(result['comparison']['method'],'tradeoff_table')
        self.assertTrue(all('cost_max' in s['critical_missing'] for s in result['scenarios']))


if __name__=='__main__':unittest.main()
