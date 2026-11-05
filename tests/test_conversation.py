"""v5.6 tests; all hypothetical numerical/source fixtures stay in temporary DBs."""
from datetime import date,timedelta
import json
from pathlib import Path
import shutil
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import main
from fastapi.testclient import TestClient
from src.data.prepare import ROOT
from src.agent.conversation import ConversationAgent
from src.agent.dialogue_memory import apply,fact,from_context,tool_context
from src.agent.dialogue_types import DialogueState,NLUProposal
from src.agent.nlu import extract
from src.agent.providers import HybridLLM,JSONProvider,ProviderError
from src.agent.tools import ToolRegistry
from src.market.api import create_app
from src.market.store import Store
from src.recommendations.retrieval import Document,import_document,retrieve


class NLUTests(unittest.TestCase):
    def test_requested_multilingual_quantities_are_not_density_guesses(self):
        cases=[('800 литров навоза','manure',800,'L'),('5 кг коровьего навоза','cattle_manure',5,'kg'),
            ('2 cubic metres of cattle manure','cattle_manure',2,'m3'),('Менде 800 литр көң бар','manure',800,'L'),
            ('5 кг тағам қалдықтары','food_waste',5,'kg'),('2 тонны свиного навоза','swine_manure',2,'t'),('500 граммов пищевых отходов','food_waste',500,'g')]
        for text,material,quantity,unit in cases:
            with self.subTest(text=text):
                state=apply(DialogueState(),extract(text))
                self.assertEqual(state.value('material'),material);self.assertEqual(state.value('quantity'),quantity);self.assertEqual(state.value('unit'),unit)
                if unit in {'L','m3'}:self.assertIsNone(state.value('mass_kg'))

    def test_subtype_followup_and_negated_material_correction(self):
        state=apply(DialogueState(),extract('800 литров навоза'))
        for reply,expected in [('Коровий','cattle_manure'),('Свиной','swine_manure'),('Птичий','poultry_manure'),('Сиырдікі','cattle_manure')]:
            refined=apply(state,extract(reply,state));self.assertEqual(refined.value('material'),expected);self.assertEqual(refined.value('quantity'),800)
        changed=apply(state,extract('Нет, это не коровий, а свиной навоз',state));self.assertEqual(changed.value('material'),'swine_manure')

    def test_temperature_updates_current_batch_and_does_not_become_material_quantity(self):
        state=apply(DialogueState(),extract('800 литров коровьего навоза'))
        updated=apply(state,extract('А если температура 37 градусов?',state))
        self.assertEqual(updated.value('temperature_c'),37);self.assertEqual(updated.value('quantity'),800);self.assertEqual(updated.value('unit'),'L')

    def test_source_and_reactor_volumes_are_distinct(self):
        state=apply(DialogueState(),extract('У меня 800 литров навоза и реактор на 90 литров'))
        self.assertEqual(state.value('material_volume_l'),800);self.assertEqual(state.value('reactor_total_volume_l'),90)
        self.assertIsNone(state.value('reactor_working_volume_l'));self.assertIsNone(state.value('mass_kg'))

    def test_reported_gas_and_methane_are_not_reactor_or_feedstock_volume(self):
        state=apply(DialogueState(),extract('Получено метана 2 м3, объём биогаза 4 м3'))
        self.assertEqual(state.value('reported_methane_volume_m3'),2);self.assertEqual(state.value('reported_biogas_volume_m3'),4)
        self.assertIsNone(state.value('quantity'));self.assertIsNone(state.value('reactor_total_volume_l'))

    def test_methane_reactor_capacity_and_prior_vs_percent_are_not_gas_or_vs_mass(self):
        state=apply(DialogueState(),extract('Метановый реактор объёмом 90 литров'))
        self.assertEqual(state.value('reactor_total_volume_l'),90);self.assertIsNone(state.value('reported_methane_volume_m3'))
        state=apply(DialogueState(),extract('VS 80%, масса 5 кг пищевых отходов'))
        self.assertIsNone(state.value('vs_mass_kg'));self.assertEqual(state.value('mass_kg'),5)

    def test_explicit_density_and_percent_basis_only(self):
        state=apply(DialogueState(),extract('800 литров коровьего навоза'))
        state=apply(state,extract('Плотность 0,95 кг/л',state))
        self.assertAlmostEqual(state.value('mass_kg'),760)
        state=apply(state,extract('TS 8%, VS 80% от TS',state))
        self.assertAlmostEqual(state.value('vs_mass_kg'),48.64)
        self.assertEqual(state.derived['vs_mass_kg'].provenance,'CALCULATED_FROM_CONFIRMED')
        self.assertEqual(state.facts['density_kg_l'].provenance,'USER_CONFIRMED')

    def test_vs_percentage_without_denominator_does_not_give_vs_mass(self):
        state=apply(DialogueState(),extract('5 кг пищевых отходов'))
        state=apply(state,extract('VS 80%',state));self.assertIsNone(state.value('vs_mass_kg'))

    def test_weighed_mass_keeps_previously_reported_volume(self):
        state=apply(DialogueState(),extract('800 литров коровьего навоза'))
        state=apply(state,extract('Я взвесил: масса 760 кг',state))
        self.assertEqual(state.value('quantity'),800);self.assertEqual(state.value('unit'),'L');self.assertEqual(state.value('mass_kg'),760)

    def test_sale_offer_retains_unknown_scope(self):
        state=apply(DialogueState(),extract('Я могу продать его за 15 000 тенге'))
        self.assertEqual(state.value('sale_offer_amount'),15000);self.assertEqual(state.value('sale_offer_currency'),'KZT')
        self.assertIsNone(state.value('sale_offer_scope'))
        state=apply(state,extract('За всю партию',state));self.assertEqual(state.value('sale_offer_scope'),'batch')

    def test_assumptions_and_examples_never_become_user_confirmed(self):
        for text in ['Допустим, 5 кг пищевых отходов','For example, 5 kg food waste','Мысалы, 5 кг тағам қалдықтары']:
            state=apply(DialogueState(),extract(text));self.assertIsNone(state.value('quantity'));self.assertEqual(state.assumptions['quantity'].provenance,'ASSUMED_FOR_SCENARIO')

    def test_profile_region_is_preserved_but_explicit_region_removes_the_assumption(self):
        state=DialogueState();state.assumptions['market_region']=fact('KZ-Almaty',provenance='ASSUMED_FOR_SCENARIO')
        self.assertEqual(tool_context(state)['market_region'],'KZ-Almaty')
        changed=apply(state,extract('I am in Karaganda. What are the market prices?',state))
        self.assertEqual(tool_context(changed)['market_region'],'KZ-Karaganda');self.assertNotIn('market_region',changed.assumptions)

    def test_conversational_region_cases_resolve_and_can_be_corrected(self):
        cases=[('В Карагандинской','KZ-Karaganda-oblast'),('В Карагандинской области','KZ-Karaganda-oblast'),
            ('В Караганде','KZ-Karaganda'),('Я из Алматы','KZ-Almaty'),('Алматинская','KZ-Almaty-oblast'),
            ('В Абайском районе','KZ-Karaganda-Abay-district')]
        for text,expected in cases:
            with self.subTest(text=text):
                state=apply(DialogueState(),extract(text))
                self.assertEqual(state.value('market_region'),expected)
                self.assertEqual(state.facts['market_region'].provenance,'USER_CONFIRMED')
        state=apply(DialogueState(),extract('В Алматы'))
        corrected=apply(state,extract('Нет, в Карагандинской',state))
        self.assertEqual(corrected.value('market_region'),'KZ-Karaganda-oblast')

    def test_invalid_units_ranges_and_working_volume_are_rejected(self):
        for text in ['-800 литров навоза','TS 101%','температура -300 градусов','{"mass_kg": true}']:
            with self.subTest(text=text),self.assertRaises(ValueError):apply(DialogueState(),extract(text))
        state=apply(DialogueState(),extract('Реактор 90 литров'))
        with self.assertRaises(ValueError):apply(state,extract('Рабочий объём 100 литров',state))

    def test_structured_pydantic_context_can_keep_both_volume_and_mass(self):
        state=apply(DialogueState(),extract(json.dumps({'material':'cattle_manure','quantity':800,'unit':'L','mass_kg':760})))
        self.assertEqual(state.value('quantity'),800);self.assertEqual(state.value('mass_kg'),760)


class ConversationTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.store=Store(Path(temp.name)/'TEST.sqlite3')
        self.agent=ConversationAgent(llm=HybridLLM(providers=[]),registry=ToolRegistry(self.store))

    def test_first_requested_question_has_useful_guidance_and_one_clarification(self):
        reply=self.agent.ask('У меня 800 литров навоза. Лучше продать или переработать? Какую температуру поставить?')
        self.assertEqual(reply['pending_question']['id'],'manure_subtype')
        self.assertIn('35 °C',reply['answer']);self.assertIn('не доказанный оптимум',reply['answer'])
        self.assertNotIn('vs_mass_kg',reply['answer']);self.assertIsNone(self.agent.state.value('mass_kg'))
        self.assertEqual([t['tool'] for t in reply['tools']],['analyze_substrate','search_scientific_sources','recommend_conditions','get_market_prices'])

    def test_oblast_reply_is_persisted_and_market_followup_uses_it(self):
        first=self.agent.ask('У меня 5 кг пищевых отходов и реактор объёмом 90 литров. Сколько метана можно получить и выгодно ли его производить?')
        reply=self.agent.ask('В Карагандинской')
        self.assertEqual(reply['memory']['facts']['market_region']['value'],'KZ-Karaganda-oblast')
        self.assertEqual(reply['memory']['facts']['market_region']['provenance'],'USER_CONFIRMED')
        self.assertTrue(any(t.get('tool') in {'get_market_prices','compare_market_scenarios','explain_market_recommendation','evaluate_advanced_economics'} for t in reply['tools']))
        self.assertNotIn('market_region',reply.get('missing',[]))
        self.assertNotEqual(first.get('memory',{}).get('facts',{}).get('market_region',{}).get('value'),'KZ-Karaganda-oblast')

    def test_manure_followup_sale_scope_and_capacity_retention(self):
        self.agent.ask('У меня 800 литров навоза. Что выгоднее?')
        reply=self.agent.ask('Коровий')
        self.assertEqual(reply['memory']['facts']['quantity']['value'],800)
        self.assertNotEqual(reply['pending_question']['id'],'manure_subtype')
        reply=self.agent.ask('Я могу продать его за 15 000 тенге');self.assertEqual(reply['pending_question']['id'],'sale_scope')
        reply=self.agent.ask('За всю партию');self.assertIn('15 000 KZT выручки',reply['answer'])
        self.assertNotIn('calculate_profitability',[t['tool'] for t in reply['tools']])
        reply=self.agent.ask('А если реактор всего 90 литров?')
        self.assertEqual(reply['pending_question']['id'],'working_volume');self.assertIn('загрузить всё одновременно нельзя',reply['answer'])
        self.assertNotIn('9 партий',reply['answer'])

    def test_material_change_invalidates_offer_density_composition_and_estimates(self):
        self.agent.ask('800 литров коровьего навоза, что выгоднее?')
        self.agent.state.facts.update({'density_kg_l':fact(.95),'ts_percent':fact(8),'sale_offer_amount':fact(15000)})
        self.agent.state.estimates['bmp_ml_ch4_g_vs']=fact(100,provenance='MODEL_ESTIMATED')
        reply=self.agent.ask('Нет, это не коровий, а свиной навоз')
        self.assertEqual(self.agent.state.value('material'),'swine_manure');self.assertEqual(self.agent.state.value('quantity'),800)
        self.assertIsNone(self.agent.state.value('sale_offer_amount'));self.assertIsNone(self.agent.state.value('density_kg_l'))
        self.assertEqual(self.agent.state.estimates,{})
        self.assertIn('sale_offer_amount',reply['technical_metadata']['invalidated_parameters'])

    def test_refining_manure_type_keeps_actual_same_batch_measurements(self):
        self.agent.ask('800 литров навоза')
        self.agent.state.facts['ts_percent']=fact(8)
        self.agent.ask('Коровий');self.assertEqual(self.agent.state.value('ts_percent'),8)

    def test_species_change_does_not_reuse_old_weighed_mass_for_the_same_litres(self):
        self.agent.ask('800 литров коровьего навоза')
        self.agent.ask('Я взвесил: масса 760 кг')
        self.agent.ask('А если у меня свиной навоз?')
        self.assertEqual(self.agent.state.value('quantity'),800);self.assertIsNone(self.agent.state.value('mass_kg'))

    def test_temperature_change_invalidates_previous_heating_costs(self):
        self.agent.ask('Какая температура нужна для коровьего навоза?')
        self.agent.ask('Температура 35 градусов')
        self.agent.state.facts['heating_cost']=fact(10)
        self.agent.ask('А если температура 37 градусов?')
        self.assertIsNone(self.agent.state.value('heating_cost'))

    def test_temperature_only_runs_the_three_requested_scientific_tools(self):
        reply=self.agent.ask('Какая температура нужна для коровьего навоза?')
        self.assertEqual([t['tool'] for t in reply['tools']],['analyze_substrate','search_scientific_sources','recommend_conditions'])
        self.assertEqual(reply['technical_metadata']['deferred_tools'],[])

    def test_no_repeated_question_after_explicitly_unknown_input(self):
        self.agent.ask('800 литров коровьего навоза. Что выгоднее?')
        reply=self.agent.ask('Не знаю')
        self.assertEqual(self.agent.state.facts['sale_offer_amount'].provenance,'UNKNOWN')
        self.assertNotEqual(reply['pending_question']['id'],'sale_offer')

    def test_food_waste_has_no_fake_yield_and_has_an_explained_question(self):
        reply=self.agent.ask('У меня 5 кг пищевых отходов. Сколько получится метана?')
        results={t['tool']:t['result'] for t in reply['tools']}
        self.assertFalse(results['predict_bmp']['model_called']);self.assertNotIn('calculate_methane',results)
        self.assertIn('органичес',reply['answer']);self.assertNotIn('bmp_ml_ch4_g_vs',reply['answer'])
        self.assertTrue(reply['user_facing_answer']['sources'])

    def test_black_soil_is_not_assigned_bmp_or_a_heater_setting(self):
        reply=self.agent.ask('Можно ли переработать чернозём?')
        self.assertIn('почва',reply['answer']);self.assertNotIn('35 °C',reply['answer'])
        self.assertFalse(any(t['result'].get('model_called') for t in reply['tools']))

    def test_supported_model_and_measured_vs_keep_the_original_calculator(self):
        measured=json.loads((ROOT/'examples/stage1_5_measured.json').read_text(encoding='utf-8'))
        self.agent=ConversationAgent(context={**measured,'vs_mass_kg':2},llm=HybridLLM(providers=[]),registry=ToolRegistry(self.store))
        reply=self.agent.ask('BMP и потенциальный метан')
        results={t['tool']:t['result'] for t in reply['tools']}
        self.assertTrue(results['predict_bmp']['model_called']);self.assertAlmostEqual(results['calculate_methane']['potential_methane_m3'],results['predict_bmp']['bmp']*.002)
        self.assertEqual(reply['memory']['estimates']['bmp_ml_ch4_g_vs']['provenance'],'MODEL_ESTIMATED')
        self.assertNotIn('bmp_ml_ch4_g_vs',reply['technical_metadata']['confirmed_parameters'])

    def test_user_measured_bmp_does_not_need_an_inapplicable_model(self):
        self.agent=ConversationAgent(context={'material':'food_waste','bmp_ml_ch4_g_vs':100,'vs_mass_kg':2,'bmp_unit':'mL CH4/g VS','gas_volume_basis':'TEST explicit reference conditions'},llm=HybridLLM(providers=[]),registry=ToolRegistry(self.store))
        reply=self.agent.ask('Сколько метана?');results={t['tool']:t['result'] for t in reply['tools']}
        self.assertNotIn('predict_bmp',results);self.assertAlmostEqual(results['calculate_methane']['potential_methane_m3'],.2)

    def test_hypothetical_economics_uses_only_explicit_assumptions(self):
        # FICTITIOUS mathematical scenario, not a market quote or installation.
        reply=self.agent.ask('Допустим, условный сценарий: mass_kg=10 sale_price_per_kg=2 potential_methane_m3=3 recovery_fraction=0.5 methane_price_per_m3=20 preparation_cost=1 heating_cost=2 operating_cost=3 currency=KZT price_date=2026-10-28 gas_volume_basis=TEST price_gas_volume_basis=TEST. Какая прибыль?')
        results={t['tool']:t['result'] for t in reply['tools']}
        self.assertEqual(results['calculate_profitability']['processing_net_profit'],24)
        self.assertIsNone(results['calculate_profitability']['final_recommendation'])
        self.assertEqual(reply['technical_metadata']['confirmed_parameters'],{})
        self.assertIn('предположения',reply['answer'])
        self.assertEqual(len(self.store.prices(include_test=True)),0)

    def test_one_ready_processing_option_is_not_blocked_by_other_missing_quotes(self):
        from src.agent.dialogue_tools import market_compare_ready
        from test_market import fixture,scenario_input
        for commodity,source_id,category,unit in [('electricity','test_power','electricity','kWh'),('raw_biogas','test_gas','natural_gas','m3'),('digestate','test_fert','organic_fertilizer','kg')]:
            with self.subTest(commodity=commodity),tempfile.TemporaryDirectory() as temp:
                store=Store(Path(temp)/'TEST.sqlite3')
                store.add_source(dict(id=source_id,name='FICTITIOUS TEST source',url='https://example.invalid/TEST',category=category))
                store.import_prices([fixture(commodity,10,unit,source_id)])
                data={**scenario_input(),'energy_use_kwh':0}
                self.assertTrue(market_compare_ready(store,{'market_scenario':data},{}))

    def test_llm_guessed_cow_and_mass_are_rejected_by_grounding(self):
        llm=HybridLLM(providers=[])
        proposal=NLUProposal(language='ru',intents=['economic_comparison'],material='cattle_manure',material_evidence='навоза',entities=[{'name':'mass_kg','text':'800 литров навоза'}])
        self.agent.llm=llm
        with patch.object(llm,'interpret',return_value=proposal):reply=self.agent.ask('800 литров навоза. Что выгоднее?')
        self.assertEqual(self.agent.state.value('material'),'manure');self.assertIsNone(self.agent.state.value('mass_kg'))
        self.assertTrue(reply['technical_metadata']['grounding_rejections'])

    def test_invalid_input_does_not_mutate_confirmed_memory(self):
        self.agent.ask('5 кг пищевых отходов')
        previous=self.agent.state.model_dump()
        reply=self.agent.ask('-800 литров навоза')
        self.assertEqual(reply['mode'],'input_rejected');self.assertEqual(self.agent.state.model_dump(),previous)

    def test_multilingual_answers_retain_language(self):
        for message,language,word in [('What temperature for cattle manure?','en','literature'),('Сиыр көңіне қандай температура керек?','kk','әдеби')]:
            agent=ConversationAgent(llm=HybridLLM(providers=[]),registry=ToolRegistry(self.store))
            reply=agent.ask(message);self.assertEqual(reply['memory']['language'],language);self.assertIn(word,reply['answer'].casefold())


class RetrievalAndProviderTests(unittest.TestCase):
    def test_structured_retrieval_filters_topics_materials_and_scope(self):
        data=retrieve('температура коровьего навоза',material='cattle_manure',topics=['temperature'])
        self.assertTrue(data['claims']);self.assertTrue(all('temperature' in c['topics'] for c in data['claims']))
        self.assertTrue(all(c['scope'] for c in data['claims']))
        self.assertTrue(any(s.get('year')==1992 and s.get('doi') is None for s in data['sources']))
        self.assertEqual(retrieve('неизвестный реактив',material='unknown_material',topics=['temperature'])['claims'],[])

    def test_validated_scientific_import_is_append_only_and_not_automatic_fact_checking(self):
        # TEST publication, explicitly fictitious; written only under a temp root.
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);(base/'data/knowledge').mkdir(parents=True)
            shutil.copyfile(ROOT/'data/knowledge/claims_v5_6.json',base/'data/knowledge/claims_v5_6.json')
            document={'version':'TEST','sources':[{'id':'test_source','title':'FICTITIOUS TEST source','url':'https://example.invalid/TEST','year':2020,'doi':None,'locator':'TEST only','reviewed_by':'TEST operator','verified_on':'2020-01-01'}],
                'claims':[{'id':'test_claim','source_id':'test_source','topics':['temperature'],'materials':['TEST_material'],'category':'TEST','process_type':'TEST','values':[], 'unit':None,'scope':'FICTITIOUS test scope only','text':{'ru':'TEST','en':'TEST','kk':'TEST'}}]}
            path=base/'test.json';path.write_text(json.dumps(document),encoding='utf-8')
            with patch('src.recommendations.retrieval.ROOT',base):
                self.assertEqual(import_document(path)['status'],'imported');self.assertEqual(import_document(path)['status'],'duplicate')
                altered={**document,'version':'TEST_changed'};path.write_text(json.dumps(altered),encoding='utf-8')
                with self.assertRaises(ValueError):import_document(path)

    def test_scientific_source_requires_review_and_valid_identifiers(self):
        data=json.loads((ROOT/'data/knowledge/claims_v5_6.json').read_text(encoding='utf-8'))
        for modification in [{'doi':'not-a-doi'},{'url':'http://example.invalid/TEST'},{'verified_on':(date.today()+timedelta(days=2)).isoformat()},{'reviewed_by':''}]:
            changed=json.loads(json.dumps(data));changed['sources'][0].update(modification)
            with self.assertRaises(ValueError):Document.model_validate(changed)

    def test_scientific_numerical_text_must_match_declared_source_bound_values(self):
        changed=json.loads((ROOT/'data/knowledge/claims_v5_6.json').read_text(encoding='utf-8'))
        changed['claims'][0]['text']['en']='TEST unsupported optimum 99 degrees'
        with self.assertRaises(ValueError):Document.model_validate(changed)

    def test_one_json_retry_and_no_network_retry(self):
        valid={'language':'ru','intents':['general'],'material':None,'material_evidence':None,'entities':[]}
        provider=JSONProvider('offline')
        responses=[{'message':{'content':'not JSON'}},{'message':{'content':json.dumps(valid)}}]
        with patch('src.agent.providers.request_json',side_effect=responses) as request:
            self.assertEqual(provider.extract_dialogue('TEST',{}).language,'ru');self.assertEqual(request.call_count,2)
        with patch('src.agent.providers.request_json',side_effect=ProviderError('TEST no connection')) as request:
            with self.assertRaises(ProviderError):provider.extract_dialogue('TEST',{})
            self.assertEqual(request.call_count,1)

    def test_compact_ordering_never_sends_large_price_results(self):
        provider=JSONProvider('offline');results={'get_market_prices':{'status':'ok','message':'TEST brief','prices':['TEST'*10000]}}
        with patch('src.agent.providers.request_json',return_value={'message':{'content':'{"order":["get_market_prices"]}'}}) as request:
            self.assertEqual(provider.order_results('TEST',results),['get_market_prices'])
        payload=request.call_args.args[1]
        self.assertLess(len(json.dumps(payload)),2500);self.assertNotIn('prices',json.loads(payload['messages'][1]['content'])['tool_results']['get_market_prices'])


class ConversationAPITests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.path=Path(temp.name)/'TEST.sqlite3';self.store=Store(self.path)
        self.client=TestClient(create_app(self.store,scheduler_enabled=False));self.client.__enter__();self.addCleanup(self.client.__exit__,None,None,None)
        self.sid=self.client.post('/api/dashboard/chat/sessions',json={'mode':'no_llm','conversation_version':'5.6'}).json()['id']

    def send(self,message,ident='TEST_dialogue_001'):
        return self.client.post(f'/api/dashboard/chat/sessions/{self.sid}/messages',json={'message':message,'request_id':ident})

    def test_structured_memory_and_turn_provenance_persist_in_existing_sqlite(self):
        first=self.send('800 литров навоза. Что выгоднее?').json()
        second=self.send('Коровий','TEST_dialogue_002').json()
        self.assertEqual(second['memory']['facts']['quantity']['value'],800)
        with TestClient(create_app(Store(self.path),scheduler_enabled=False)) as client:
            session=client.get(f'/api/dashboard/chat/sessions/{self.sid}').json()
        self.assertEqual(len(session['turns']),2);self.assertEqual(session['memory']['facts']['material']['value'],'cattle_manure')
        with self.store.connect() as con:row=con.execute('SELECT * FROM dashboard_turns WHERE session_id=? ORDER BY id DESC',(self.sid,)).fetchone()
        self.assertIsNotNone(row['extracted_entities_json']);self.assertIsNotNone(row['confirmed_parameters_json']);self.assertIsNotNone(row['pending_question_json']);self.assertIsNotNone(row['tool_results_json'])

    def test_retry_is_idempotent_for_new_conversations(self):
        first=self.send('5 кг пищевых отходов. Сколько метана?').json();second=self.send('5 кг пищевых отходов. Сколько метана?').json()
        self.assertEqual(first,second)
        with self.store.connect() as con:self.assertEqual(con.execute('SELECT count(*) FROM dashboard_turns WHERE session_id=?',(self.sid,)).fetchone()[0],1)

    def test_upgrade_preserves_old_messages_and_explicit_facts(self):
        old=self.client.post('/api/dashboard/chat/sessions',json={'mode':'no_llm','context':{'material':'cattle_manure','material_volume_l':800}}).json()['id']
        self.client.post(f'/api/dashboard/chat/sessions/{old}/messages',json={'message':'Какая температура?','request_id':'TEST_old_request'})
        before=self.client.get(f'/api/dashboard/chat/sessions/{old}').json()
        after=self.client.post(f'/api/dashboard/chat/sessions/{old}/upgrade').json()
        self.assertEqual(after['conversation_version'],'5.6');self.assertEqual(after['turns'][0]['reply'],before['turns'][0]['reply'])
        self.assertEqual(after['memory']['facts']['quantity']['value'],800)

    def test_local_llm_unavailable_has_controlled_human_fallback(self):
        sid=self.client.post('/api/dashboard/chat/sessions',json={'mode':'offline','conversation_version':'5.6'}).json()['id']
        with patch('src.agent.providers.JSONProvider.extract_dialogue',side_effect=ProviderError('TEST Ollama unavailable')):
            response=self.client.post(f'/api/dashboard/chat/sessions/{sid}/messages',json={'message':'800 литров навоза. Что выгоднее?','request_id':'TEST_llm_unavailable'})
        data=response.json();self.assertEqual(data['mode'],'deterministic_tools_no_llm');self.assertEqual(data['pending_question']['id'],'manure_subtype')
        self.assertNotIn('vs_mass_kg',data['answer']);self.assertTrue(data['technical_metadata']['fallback_reason'])

    def test_no_material_or_amount_correction_loses_history(self):
        self.send('800 литров коровьего навоза')
        reply=self.send('Исправление: сырьё — свиной навоз; количество — 600 литров.','TEST_correction_002').json()
        self.assertEqual(reply['memory']['facts']['material']['value'],'swine_manure')
        self.assertEqual(reply['memory']['facts']['quantity']['value'],600)
        self.assertEqual(len(self.client.get(f'/api/dashboard/chat/sessions/{self.sid}').json()['turns']),2)

    def test_cli_resume_uses_the_same_sqlite_structured_memory(self):
        env=dict(os.environ,BIOREACTOR_MARKET_DB=str(self.path),PYTHONUTF8='1')
        first=subprocess.run([sys.executable,str(ROOT/'main.py'),'chat','--no-llm','--json','--message','800 литров навоза. Что выгоднее?'],capture_output=True,env=env,check=True)
        initial=json.loads(first.stdout);identifier=initial['memory']['conversation_id']
        second=subprocess.run([sys.executable,str(ROOT/'main.py'),'chat','--no-llm','--json','--conversation',identifier,'--message','Коровий'],capture_output=True,env=env,check=True)
        reply=json.loads(second.stdout)
        self.assertEqual(reply['memory']['facts']['quantity']['value'],800);self.assertEqual(reply['memory']['facts']['material']['value'],'cattle_manure')
        self.assertEqual(len(self.client.get(f'/api/dashboard/chat/sessions/{identifier}').json()['turns']),2)


if __name__=='__main__':unittest.main()
