"""Tool results and actual calls, not just keyword assertions in generated text."""
import json
from pathlib import Path
import sys
import unittest
import tempfile
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import main
from src.data.prepare import ROOT
from src.agent.context import extract_explicit,validate_context
from src.agent.orchestrator import Agent
from src.agent.providers import HybridLLM,JSONProvider,ProviderError
from src.agent.tools import ToolRegistry,TOOL_NAMES
from src.economics.calculator import calculate_methane,calculate_profitability
from src.recommendations.knowledge import load_knowledge,search_scientific_sources
from src.market.store import Store

_MARKET_TEMP=tempfile.TemporaryDirectory(prefix='bioreactor-agent-market-tests-')


def measured():
    return json.loads((ROOT/'examples/stage1_5_measured.json').read_text())


def no_llm(context=None):
    return Agent(context=context,llm=HybridLLM('offline',providers=[]),registry=ToolRegistry(market_store=Store(Path(_MARKET_TEMP.name)/'market.sqlite3')))


def results(reply):
    return {entry['tool']:entry['result'] for entry in reply['tools']}


class AgentToolTests(unittest.TestCase):
    def test_ordinary_organic_material_source_guidance_no_fake_bmp(self):
        reply=no_llm().ask('Пищевые отходы: какие условия и BMP?')
        r=results(reply)
        self.assertEqual(r['analyze_substrate']['material'],'food_waste')
        self.assertFalse(r['predict_bmp']['model_called'])
        self.assertEqual(r['recommend_conditions']['conditions']['ph_range'],[7,7.5])
        self.assertEqual(r['recommend_conditions']['kind'],'literature_guidance')
        self.assertNotIn('bmp',r['predict_bmp'])

    def test_chernozem_volumes_and_actual_tools(self):
        agent=no_llm()
        with patch.object(agent.registry,'execute',wraps=agent.registry.execute) as spy:
            reply=agent.ask('У меня 80 литров чернозёма и реактор на 90 литров. Выгоднее продать или переработать в биогаз?')
        names=[call.args[0] for call in spy.call_args_list]
        self.assertEqual(names,['analyze_substrate','predict_bmp','calculate_methane','get_market_prices','compare_market_scenarios','explain_market_recommendation'])
        self.assertEqual(reply['context']['material_volume_l'],80)
        self.assertEqual(reply['context']['reactor_volume_l'],90)
        self.assertNotIn('mass_kg',reply['context'])
        self.assertFalse(results(reply)['predict_bmp']['model_called'])
        self.assertEqual(results(reply)['compare_market_scenarios']['status'],'needs_input')

    def test_unknown_material_and_mixture(self):
        for material in ['unknown_lab_material','mixture','смесь соломы и навоза']:
            reply=no_llm({'material':material}).ask('Оцени BMP')
            self.assertFalse(results(reply)['predict_bmp']['model_called'])
            self.assertNotIn('bmp',results(reply)['predict_bmp'])

    def test_unspecified_manure_not_assumed_cattle(self):
        reply=no_llm().ask('У меня навоз, какие режимы?')
        self.assertEqual(reply['context']['material'],'manure_unspecified')
        self.assertEqual(results(reply)['recommend_conditions']['status'],'insufficient_evidence')

    def test_reset_preserves_model_preference_but_clears_batch(self):
        agent=no_llm({**measured(),'model':'stage1'})
        reply=agent.ask('Теперь чернозём')
        self.assertEqual(reply['context']['model'],'stage1')
        self.assertNotIn('c_vs_inoc',reply['context'])
        agent.reset()
        self.assertEqual(agent.context,{'model':'stage1'})

    def test_supported_but_incomplete(self):
        reply=no_llm().ask('BMP пшеничной соломы')
        r=results(reply)['predict_bmp']
        self.assertEqual(r['status'],'needs_input')
        self.assertIn('c_vs_inoc',r['missing'])
        self.assertFalse(r['model_called'])

    def test_real_model_and_methane_chain_both_artifacts(self):
        from src.inference.predict import predict_bmp
        for model,path in [('stage1',ROOT/'models/bmp.joblib'),('stage1_5',ROOT/'models/stage1_5/bmp.joblib')]:
            context={**measured(),'model':model,'vs_mass_kg':2}
            reply=no_llm(context).ask('BMP и потенциальный метан')
            r=results(reply)
            expected=predict_bmp(measured(),path)['bmp']
            self.assertTrue(r['predict_bmp']['model_called'])
            self.assertAlmostEqual(r['predict_bmp']['bmp'],expected)
            self.assertAlmostEqual(r['calculate_methane']['potential_methane_m3'],expected*.002)

    def test_out_of_distribution_refuses_number_for_both_artifacts(self):
        for model in ['stage1','stage1_5']:
            reply=no_llm({**measured(),'c_vs_sub_f':.991,'model':model}).ask('Оцени BMP')
            r=results(reply)['predict_bmp']
            self.assertEqual(r['status'],'out_of_distribution')
            self.assertFalse(r['model_called'])
            self.assertNotIn('bmp',r)

    def test_model_load_failure_is_explicit(self):
        with patch('joblib.load',side_effect=OSError('unreadable model')):
            r=results(no_llm(measured()).ask('BMP'))['predict_bmp']
        self.assertEqual(r['status'],'error')
        self.assertFalse(r['model_called'])
        self.assertNotIn('bmp',r)

    def test_invalid_volume_rejected_without_tool_calls_or_memory_update(self):
        agent=no_llm()
        for text in ['У меня -80 литров чернозёма','reactor_volume_l=0','reactor_volume_l=nan']:
            with patch.object(agent.registry,'execute',wraps=agent.registry.execute) as spy:
                reply=agent.ask(text)
            self.assertEqual(reply['mode'],'input_rejected')
            spy.assert_not_called()
            self.assertEqual(agent.context,{})

    def test_units_not_silently_converted(self):
        r=no_llm().ask(json.dumps({'mass_kg':3,'units':{'mass_kg':'L'}}))
        self.assertEqual(r['mode'],'input_rejected')
        with self.assertRaises(ValueError):
            calculate_methane({'bmp_ml_ch4_g_vs':300,'vs_mass_kg':1,'bmp_unit':'mL/g TS','gas_volume_basis':'specified'})

    def test_missing_prices_never_default_to_zero(self):
        r=ToolRegistry().execute('calculate_profitability',{'mass_kg':5},{},'')
        self.assertEqual(r['status'],'needs_input')
        self.assertIn('sale_price_per_kg',r['missing'])
        self.assertNotIn('processing_net_profit',r)

    def test_economic_arithmetic_explicit_test_scenario_not_market_data(self):
        # Mathematical fixture only: these are not claimed market prices.
        data={'mass_kg':10,'sale_price_per_kg':2,'potential_methane_m3':3,'recovery_fraction':.5,
            'methane_price_per_m3':20,'preparation_cost':1,'heating_cost':2,'operating_cost':3,
            'currency':'TEST','price_date':'2026-10-28','gas_volume_basis':'same test basis','price_gas_volume_basis':'same test basis'}
        r=ToolRegistry().execute('calculate_profitability',data,{},'')
        self.assertEqual(r['sale_revenue'],20)
        self.assertEqual(r['recoverable_methane_m3'],1.5)
        self.assertEqual(r['methane_revenue'],30)
        self.assertEqual(r['processing_net_profit'],24)
        self.assertEqual(r['difference_processing_minus_sale'],4)
        self.assertEqual(r['currency'],'TEST')
        for bad in [{'recovery_fraction':1.1},{'heating_cost':-1},{'price_date':'not-a-date'},{'mass_kg':True},{'price_gas_volume_basis':'different basis'}]:
            self.assertEqual(ToolRegistry().execute('calculate_profitability',{**data,**bad},{},'')['status'],'error')

    def test_measured_bmp_not_overwritten_by_model(self):
        context={'bmp_ml_ch4_g_vs':100,'vs_mass_kg':2,'bmp_unit':'mL CH4/g VS','gas_volume_basis':'explicit basis'}
        r=ToolRegistry().execute('calculate_methane',context,{'predict_bmp':{'status':'ok','bmp':999}},'')
        self.assertEqual(r['potential_methane_m3'],.2)

    def test_multi_turn_facts_then_predict(self):
        agent=no_llm()
        first=agent.ask('BMP пшеничной соломы')
        self.assertIn('c_vs_sub_m',first['missing'])
        second=agent.ask(json.dumps(measured()))
        self.assertTrue(results(second)['predict_bmp']['model_called'])
        third=agent.ask('Теперь чернозём')
        self.assertNotIn('c_vs_sub_m',third['context'])
        self.assertFalse(results(third).get('predict_bmp',{}).get('model_called',False))

    def test_mock_status_has_no_fake_readings_or_control(self):
        r=results(no_llm().ask('Статус датчиков'))['get_reactor_status']
        self.assertEqual(r['mode'],'mock')
        self.assertFalse(r['connected'])
        self.assertIsNone(r['readings'])
        self.assertIsNone(r['measured_at'])
        self.assertFalse(r['actuator_access'])
        self.assertEqual(ToolRegistry().execute('set_heater',{}, {},'')['code'],'tool_not_allowed')

    def test_knowledge_has_sources_and_unknown_composition_not_filled(self):
        kb=load_knowledge()
        for record in kb['materials'].values():
            self.assertIsNone(record['dry_matter_fraction'])
            self.assertIsNone(record['vs_fraction'])
            for source in record['sources']: self.assertIn(source,kb['sources'])
        r=search_scientific_sources('BMP VS Hafner')
        self.assertTrue(any(s['id']=='hafner' for s in r['sources']))
        self.assertFalse(r['live_web_search'])
        self.assertEqual(search_scientific_sources('xyzz_unlisted_compound')['sources'],[])


class ProviderTests(unittest.TestCase):
    def test_structured_followup_does_not_start_unrelated_llm_tools(self):
        provider=JSONProvider('offline')
        responses=[{'message':{'content':'{"tools":["predict_bmp"]}'}},
                   {'message':{'content':'{"order":["analyze_substrate","predict_bmp"]}'}},
                   {'message':{'content':json.dumps({'tools':TOOL_NAMES})}},
                   {'message':{'content':'{"order":["analyze_substrate","predict_bmp"]}'}}]
        agent=Agent(llm=HybridLLM(providers=[provider]))
        with patch('src.agent.providers.request_json',side_effect=responses):
            agent.ask('BMP пшеничной соломы')
            reply=agent.ask(json.dumps(measured()))
        self.assertEqual(reply['llm_proposed_tools'],TOOL_NAMES)
        self.assertEqual([t['tool'] for t in reply['tools']],['analyze_substrate','predict_bmp'])
        self.assertTrue(results(reply)['predict_bmp']['model_called'])
    def test_no_internet_and_no_local_llm_tools_remain_available(self):
        providers=[JSONProvider('online',model='test-model',key='test-key'),JSONProvider('offline')]
        with patch('src.agent.providers.request_json',side_effect=ProviderError('connection unavailable')):
            reply=Agent(llm=HybridLLM(providers=providers)).ask('Статус датчиков')
        self.assertEqual(reply['mode'],'deterministic_tools_no_llm')
        self.assertFalse(results(reply)['get_reactor_status']['connected'])
        self.assertEqual(len(reply['provider_status']),2)

    def test_online_unavailable_falls_back_to_local(self):
        online=JSONProvider('online',model='test-model',key='test-key')
        local=JSONProvider('offline')
        def response(url,payload,timeout,key):
            if key: raise ProviderError('network unavailable')
            text='{"tools":["get_reactor_status"]}' if 'планировщик' in payload['messages'][0]['content'] else '{"order":["get_reactor_status"]}'
            return {'message':{'content':text}}
        with patch('src.agent.providers.request_json',side_effect=response) as spy:
            reply=Agent(llm=HybridLLM(providers=[online,local])).ask('Статус датчиков')
        self.assertEqual(reply['mode'],'llm_tools')
        self.assertEqual(reply['provider_status'][1]['provider'],'offline')
        self.assertEqual(spy.call_count,3)

    def test_both_adapter_payloads_and_real_python_tool_dispatch(self):
        for kind in ['offline','online']:
            provider=JSONProvider(kind,model='test-model',key='test-key' if kind=='online' else None)
            def response(url,payload,timeout,key):
                content='{"tools":["get_reactor_status"]}' if 'планировщик' in payload['messages'][0]['content'] else '{"order":["get_reactor_status"]}'
                return {'message':{'content':content}} if kind=='offline' else {'choices':[{'message':{'content':content}}]}
            with patch('src.agent.providers.request_json',side_effect=response) as spy, patch.object(provider,'_model_resident',return_value=True):
                reply=Agent(llm=HybridLLM(kind,providers=[provider])).ask('Статус датчиков')
            self.assertEqual(reply['mode'],'llm_tools')
            self.assertEqual(results(reply)['get_reactor_status']['mode'],'mock')
            self.assertEqual(spy.call_count,2)

    def test_malicious_tool_plan_fails_closed(self):
        provider=JSONProvider('offline')
        with patch('src.agent.providers.request_json',return_value={'message':{'content':'{"tools":["set_heater"]}'}}):
            reply=Agent(llm=HybridLLM(providers=[provider])).ask('Статус датчиков')
        self.assertEqual(reply['mode'],'deterministic_tools_no_llm')
        self.assertEqual([r['tool'] for r in reply['tools']],['get_reactor_status'])

    def test_llm_invented_numbers_and_free_text_never_enter_outputs(self):
        provider=JSONProvider('offline')
        with patch('src.agent.providers.request_json',return_value={'message':{'content':'{"tools":["get_reactor_status"],"mass_kg":999,"answer":"temperature 999"}'}}):
            reply=Agent(llm=HybridLLM(providers=[provider])).ask('Статус датчиков')
        self.assertNotIn('mass_kg',reply['context'])
        self.assertNotIn('999',reply['answer'])
        self.assertIsNone(results(reply)['get_reactor_status']['readings'])

    def test_no_config_no_network_and_no_key_leak(self):
        provider=JSONProvider('online',model='test',key='')
        with patch('src.agent.providers.request_json') as spy:
            status=HybridLLM('online',providers=[provider]).probe()
        spy.assert_not_called()
        self.assertEqual(status[0]['status'],'not_configured')


if __name__=='__main__':
    unittest.main()
