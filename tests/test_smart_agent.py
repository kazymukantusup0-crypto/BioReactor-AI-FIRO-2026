"""Intent routing, scientific boundaries and cache invalidation. TEST ONLY fixtures."""
import main
import os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from src.agent.conversation import ConversationAgent
from src.agent.providers import HybridLLM
from src.agent.tools import ToolRegistry
from src.market.store import Store
from src.research.profile_cache import read_profile

class SmartAgentTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.store=Store(Path(self.tmp.name)/'TEST.sqlite3')
  self.agent=ConversationAgent(llm=HybridLLM(providers=[]),registry=ToolRegistry(self.store),research_enabled=True)
  env=patch.dict(os.environ,{'BIOREACTOR_RESEARCH_ONLINE':'0'});env.start();self.addCleanup(env.stop)
 def ask(self,text):return self.agent.ask(text)
 def test_intake_records_quantity_and_asks_goal_without_tools(self):
  r=self.ask('У меня 100 кг коровьей навозной жижи');self.assertEqual(r['tools'],[]);self.assertEqual(self.agent.state.value('quantity'),100);self.assertEqual(r['pending_question']['id'],'smart-goal')
 def test_temperature_does_not_call_gas_economics_or_market(self):
  self.ask('У меня 100 кг коровьей навозной жижи')
  with patch('src.advisor.mixing.evaluate',side_effect=AssertionError('Unneeded gas calculation')),patch('src.advisor.service.analyze',side_effect=AssertionError('Unneeded economics')):r=self.ask('Температуру')
  self.assertIn('35',r['answer']);self.assertNotIn('м³',r['answer']);self.assertEqual([x['tool'] for x in r['tools']],['advise_substrate_conditions'])
 def test_gas_does_not_run_full_economics(self):
  with patch('src.advisor.service.analyze',side_effect=AssertionError('Unneeded economics')),patch('src.economics.complete_analysis.analyze',side_effect=AssertionError('Unneeded economics')):r=self.ask('У меня 142 литра коровьей навозной жижи. Сколько газа?')
  self.assertIn('2.92',r['answer']);self.assertEqual([x['tool'] for x in r['tools']],['estimate_substrate_gas'])
 def test_gas_without_amount_never_invents_one_kg(self):
  r=self.ask('У меня коровий навоз. Сколько газа?');self.assertNotIn('м³',r['answer']);self.assertEqual(r['tools'],[]);self.assertIn('количество',r['answer'])
 def test_duration_has_only_relevant_studies_and_no_batch_prediction(self):
  self.ask('У меня 142 литра коровьей навозной жижи. Сколько газа?');r=self.ask('Сколько дней потребуется?');self.assertIn('неизвестен',r['answer']);self.assertIn('27',r['answer']);self.assertNotIn('30',r['answer']);self.assertNotIn('₸',r['answer'])
 def test_unknown_grass_duration_does_not_borrow_manure_days(self):
  r=self.ask('У меня 20 кг травы. Сколько дней?');self.assertNotIn('27',r['answer']);self.assertNotIn('30',r['answer'])
 def test_cache_reuses_result_but_new_quantity_invalidates_gas(self):
  first=self.ask('У меня 100 кг коровьей навозной жижи. Сколько газа?');r=self.ask('А теперь сколько газа?');self.assertTrue(r['tools'][0]['cache_hit']);self.assertEqual(first['answer'],r['answer'])
  r=self.ask('У меня 200 кг коровьей навозной жижи. Сколько газа?');self.assertFalse(r['tools'][0]['cache_hit']);self.assertNotEqual(first['answer'],r['answer'])
 def test_detail_and_one_sentence_explain_same_result_without_execution(self):
  self.ask('У меня 100 кг коровьей навозной жижи. Сколько газа?');r=self.ask('Объясни подробнее');self.assertIn('Формула',r['answer']);self.assertEqual(r['tools'],[])
  r=self.ask('Ответь одним предложением');self.assertEqual(r['tools'],[]);self.assertEqual(r['answer'].count('. '),0);self.assertNotIn('Формула',r['answer'])
 def test_followups_keep_real_mixture_and_only_requested_goal(self):
  self.ask('У меня 142 литра коровьей навозной жижи. Сколько газа?');self.ask('Какая температура лучше?');self.ask('Добавь 20 кг пищевых отходов');r=self.ask('А теперь сколько газа?')
  self.assertEqual([(x['quantity'],x['unit']) for x in self.agent.state.mixture_components],[(142,'L'),(20,'kg')]);self.assertIn('2.92',r['answer']);self.assertIn('Полный выход пока не рассчитан',r['answer']);self.assertNotIn('35',r['answer']);self.assertEqual(len(r['tools']),1)
 def test_what_if_addition_remains_active_without_changing_confirmed_stock(self):
  self.ask('У меня 100 кг коровьей навозной жижи');self.ask('Температуру');self.ask('А если добавить 20 кг пищевых отходов?');r=self.ask('А сколько получится газа?')
  self.assertEqual(len(self.agent.state.mixture_components),1);self.assertEqual(len(self.agent.state.mixture_scenario_components),2);self.assertTrue(self.agent.state.active_mixture_scenario);self.assertIn('2.03',r['answer']);self.assertIn('Полный выход пока не рассчитан',r['answer'])
 def test_economics_only_does_not_repeat_gas_temperature_or_composition(self):
  self.ask('У меня 100 кг коровьей навозной жижи');r=self.ask('А выгодно?');self.assertNotIn('35',r['answer']);self.assertNotIn('TS',r['answer']);self.assertEqual([x['tool'] for x in r['tools']],['research_and_estimate'])
 def test_explicit_economic_explanation_cannot_reuse_a_gas_only_result(self):
  self.ask('У меня 100 кг коровьей навозной жижи. Сколько газа?');r=self.ask('Объясни, выгодно ли перерабатывать?')
  self.assertEqual([x['tool'] for x in r['tools']],['research_and_estimate']);self.assertIn('economics',r['technical_metadata']['intent_plan']['goals'])
 def test_reactor_question_has_one_read_only_tool(self):
  self.ask('У меня 100 кг коровьей навозной жижи');r=self.ask('Какое состояние реактора?');self.assertEqual([x['tool'] for x in r['tools']],['get_reactor_status']);self.assertFalse(r['actuator_access'])
 def test_definition_is_not_gas_yield_request(self):
  self.ask('У меня 100 кг коровьей навозной жижи');r=self.ask('Что такое биогаз?');self.assertEqual(r['tools'],[]);self.assertIn('без кислорода',r['answer']);self.assertNotIn('м³',r['answer'])
 def test_sources_explain_actual_result_without_recalculating(self):
  self.ask('У меня 142 литра коровьей навозной жижи. Сколько газа?');r=self.ask('Откуда эти числа?');self.assertEqual(r['tools'],[]);self.assertTrue(any('s43153' in s['url'] for s in r['user_facing_answer']['sources']));self.assertIsNone(r['pending_question'])
 def test_ambiguous_why_question_is_sent_to_llm_for_task_selection(self):
  from src.agent.dialogue_types import NLUProposal
  self.ask('У меня 100 кг коровьей навозной жижи. Сколько газа?')
  proposal=NLUProposal(language='ru',intents=['reactor_status'],material=None,material_evidence=None,entities=[])
  with patch.object(self.agent.llm,'interpret',return_value=proposal) as interpret:r=self.ask('Почему он не работает?')
  interpret.assert_called_once();self.assertEqual([x['tool'] for x in r['tools']],['get_reactor_status'])
 def test_source_lookup_with_no_prior_calculation_does_not_compute_gas(self):
  self.ask('У меня 100 кг коровьей навозной жижи');r=self.ask('Какие источники?');self.assertEqual([x['tool'] for x in r['tools']],['get_substrate_catalog']);self.assertNotIn('м³',r['answer'])
 def test_user_evidence_text_does_not_approve_a_handbook_value(self):
  data={'components':[{'id':'c1','material':'cattle_manure','material_state':'slurry','quantity':10,'unit':'kg'}],'decision':{'methane_fraction':{'low':.99,'high':.99,'provenance':'USER_REPORTED','evidence':'TEST ONLY user statement mentioning FNR'}}}
  r=ToolRegistry(self.store).execute('estimate_substrate_gas',{'advisor_request':data},{},'TEST')
  self.assertFalse(any(s.get('id','').startswith('fnr-cattle') for s in r['sources']))
 def test_unsupported_material_does_not_get_fake_source(self):
  self.ask('У меня 20 кг травы. Сколько газа?');r=self.ask('Откуда эти числа?');self.assertFalse(r['user_facing_answer']['sources']);self.assertIn('пока нет',r['answer'])
 def test_cache_survives_state_storage_without_public_memory_bloat(self):
  r=self.ask('У меня 142 литра коровьей навозной жижи. Сколько газа?');self.assertNotIn('smart_cache',r['memory'])
  self.agent=ConversationAgent(llm=HybridLLM(providers=[]),registry=ToolRegistry(self.store),state=self.agent.state.model_dump(mode='json'),research_enabled=True)
  self.assertTrue(self.ask('Сколько газа?')['tools'][0]['cache_hit'])
 def test_profile_file_cache_invalidates_and_cannot_be_mutated_by_caller(self):
  path=Path(self.tmp.name)/'TEST_profile.json';path.write_text('{"value":1}',encoding='utf-8');a=read_profile(path);a['value']=999;self.assertEqual(read_profile(path)['value'],1)
  path.write_text('{"value":22}',encoding='utf-8');self.assertEqual(read_profile(path)['value'],22)
 def test_condition_cache_preserves_actual_quantity_in_audit(self):
  r=self.ask('У меня 100 литров коровьей навозной жижи. Какая температура?');self.assertEqual(r['tools'][0]['result']['request']['components'][0]['quantity'],100)
  r=self.ask('У меня 500 литров коровьей навозной жижи. Какая температура?');self.assertTrue(r['tools'][0]['cache_hit']);self.assertEqual(r['tools'][0]['result']['request']['components'][0]['quantity'],500);self.assertEqual(r['tools'][0]['result']['geometry']['known_charge_min_l'],500)
 def test_chat_cache_invalidates_on_scientific_profile_revision(self):
  self.ask('У меня 100 кг коровьей навозной жижи. Сколько газа?')
  with patch('src.agent.smart_bridge.evidence_revision',return_value=[('TEST revision',2,100)]):r=self.ask('Сколько газа?')
  self.assertFalse(r['tools'][0]['cache_hit'])
 def test_combined_question_has_gas_conditions_but_no_economic_tool(self):
  r=self.ask('У меня 100 литров коровьей навозной жижи и 20 кг пищевых отходов. Сколько газа, при какой температуре и сколько дней?')
  self.assertEqual([x['tool'] for x in r['tools']],['estimate_substrate_gas','advise_substrate_conditions']);self.assertIn('35',r['answer']);self.assertIn('неизвестен',r['answer']);self.assertNotIn('LITERATURE_ESTIMATE',r['answer'])
 def test_conditions_tool_keeps_reactor_geometry_guard(self):
  data={'components':[{'id':'c1','material':'cattle_manure','material_state':'slurry','quantity':10,'unit':'kg'}],'reactor_total_volume_l':100,'feeding_period_days':1,'inoculum_description':'TEST culture','inoculum_adapted_temperature_c':35,'mixing_available':True,'monitoring_confirmed':True,'temperature_control_confirmed':True,'measured_ph':7.8,'decision':{'reactor':{'reactor_working_volume_l':200,'headspace_l':20,'operating_mode':'continuous','reactor_type':'CSTR','engineering_review_confirmed':True}}}
  r=ToolRegistry(self.store).execute('advise_substrate_conditions',{'advisor_request':data,'topics':['temperature']},{},'TEST')
  self.assertEqual(r['geometry']['status'],'PHYSICALLY_INFEASIBLE');self.assertIsNone(r['temperature']['candidate'])

if __name__=='__main__':unittest.main()
