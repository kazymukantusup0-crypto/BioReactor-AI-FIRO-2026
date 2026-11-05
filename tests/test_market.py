"""All numeric fixtures here are TEST prices, not market observations."""
import asyncio
import csv
from datetime import datetime,timezone
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import main
from fastapi.testclient import TestClient
from src.market.domain import PriceInput,normalize_price
from src.market.store import Store
from src.market.adapters import parse_csv,parse_esalmaty,SourceError
from src.market.updater import Updater,scheduler
from src.market.scenarios import compare,ScenarioInput
from src.market.service import price_changes
from src.market.api import create_app
from src.agent.orchestrator import Agent
from src.agent.providers import HybridLLM
from src.agent.tools import ToolRegistry


def fixture(commodity='food_waste',value=2,unit='kg',source_id='test_feed',effective='2020-01-01'):
    return dict(source_id=source_id,commodity=commodity,region='KZ-TEST',country='KZ',value=value,currency='KZT',unit=unit,
        published_at=effective,effective_from=effective,price_type='tariff' if commodity=='electricity' else 'purchase',
        reliability='test',consumer_class='non_household_group2',tax_basis='VAT_included',
        gas_volume_basis='TEST_same_basis' if unit in {'m3','1000_m3','L'} else None,
        source_url='https://example.invalid/TEST',evidence='TEST mathematical fixture; NOT a real quotation',is_test=True)


def scenario_input():
    return dict(region='KZ-TEST',currency='KZT',consumer_class='non_household_group2',tax_basis='VAT_included',
        feedstock_commodity='food_waste',mass_kg=20,potential_methane_m3=10,gas_volume_basis='TEST_same_basis',
        recovery_fraction=.5,methane_fraction=.5,methane_energy_kwh_per_m3=10,electricity_efficiency=.4,
        electricity_demand_kwh=100,energy_use_kwh=2,preparation_cost=10,heating_cost=5,operating_cost=5,
        storage_cost=2,transport_cost=3,gas_cleaning_cost=10,digestate_handling_cost=5,sale_storage_cost=1,sale_transport_cost=1,
        gas_sale_technical_confirmed=True,gas_sale_legal_confirmed=True,gas_sale_evidence='TEST assumption, not legal advice',
        digestate_mass_kg=10,digestate_quality_confirmed=True,digestate_market_allowed=True,
        digestate_quality_evidence='TEST assumption, not a quality certificate',allow_test_prices=True)


class MarketTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store=Store(Path(self.temp.name)/'test.sqlite3')
        for ident,category in [('test_feed','organic_feedstock'),('test_power','electricity'),('test_gas','natural_gas'),('test_fert','organic_fertilizer'),('test_mineral','mineral_fertilizer')]:
            self.store.add_source(dict(id=ident,name='TEST source',url='https://example.invalid/TEST',category=category,adapter='manual'))

    def populated(self):
        return self.store.import_prices([fixture(),fixture('electricity',10,'kWh','test_power'),
            fixture('raw_biogas',30,'m3','test_gas'),fixture('digestate',1,'kg','test_fert')])

    def test_save_and_duplicate_immutable_history(self):
        a=self.store.import_prices([fixture()]);b=self.store.import_prices([fixture()])
        self.assertEqual(a['inserted'],1);self.assertEqual(b['duplicates'],1)
        newer={**fixture(),'value':3,'effective_from':'2020-02-01','published_at':'2020-02-01'}
        self.store.import_prices([newer])
        self.assertEqual(len(self.store.prices(include_test=True)),2)
        with self.assertRaises(sqlite3.IntegrityError),self.store.connect() as con:
            con.execute('UPDATE observations SET value=999')
        with self.assertRaises(sqlite3.IntegrityError),self.store.connect() as con:
            con.execute('DELETE FROM observations')

    def test_equivalent_unit_duplicate(self):
        self.store.import_prices([fixture(value=2)])
        self.assertEqual(self.store.import_prices([fixture(value=2000,unit='t')])['duplicates'],1)

    def test_unit_conversion_not_commodity_substitution(self):
        self.assertEqual(normalize_price(1000,'t','digestate'),('1','kg'))
        self.assertEqual(normalize_price(1000,'MWh','electricity'),('1','kWh'))
        self.assertEqual(normalize_price(10000,'1000_m3','natural_gas'),('10','m3'))
        with self.assertRaises(ValueError):normalize_price(20,'L','food_waste')
        with self.assertRaises(ValueError):normalize_price(20,'kg','electricity')

    def test_test_labels_required_and_excluded_by_default(self):
        with self.assertRaises(ValueError):PriceInput.model_validate({**fixture(),'is_test':False})
        self.store.import_prices([fixture()])
        self.assertEqual(self.store.prices(),[])
        self.assertEqual(len(self.store.prices(include_test=True)),1)

    def test_stale_and_unknown_publication_not_current(self):
        p={**fixture(),'reliability':'verified_manual','is_test':False}
        self.store.import_prices([p])
        now=datetime(2020,3,1,tzinfo=timezone.utc)
        row=self.store.prices(now=now,latest=True)[0]
        self.assertTrue(row['is_stale']);self.assertFalse(row['usable_as_current'])
        p.update(published_at=None,effective_from='2020-02-29')
        self.store.import_prices([p])
        row=self.store.prices(now=now,latest=True)[0]
        self.assertTrue(row['publication_date_unknown']);self.assertFalse(row['usable_as_current'])

    def test_recent_but_superseded_price_never_current(self):
        base={**fixture(),'reliability':'verified_manual','is_test':False}
        self.store.import_prices([{**base,'published_at':'2020-02-20','effective_from':'2020-02-20'},
            {**base,'value':3,'published_at':'2020-02-25','effective_from':'2020-02-25'}])
        rows=self.store.prices(now=datetime(2020,3,1,tzinfo=timezone.utc))
        self.assertTrue(rows[0]['usable_as_current'])
        self.assertFalse(rows[1]['usable_as_current']);self.assertTrue(rows[1]['is_superseded'])
        # A history filter must not make a superseded quote current again.
        old=self.store.prices(end='2020-02-21',now=datetime(2020,3,1,tzinfo=timezone.utc))[0]
        self.assertTrue(old['is_superseded'])

    def test_kazakhstan_day_boundary_not_host_utc_day(self):
        p={**fixture(),'reliability':'verified_manual','is_test':False,'published_at':'2020-03-01','effective_from':'2020-03-01'}
        self.store.import_prices([p])
        rows=self.store.prices(now=datetime(2020,2,29,22,tzinfo=timezone.utc),latest=True)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['age_days'],0)
        self.assertTrue(rows[0]['usable_as_current'])

    def test_failed_update_preserves_cached_prices_and_logs_error(self):
        self.populated()
        with self.store.connect() as con:con.execute("UPDATE sources SET adapter='csv' WHERE id='test_power'")
        updater=Updater(self.store,fetcher=lambda s: (_ for _ in ()).throw(SourceError('TEST internet unavailable')))
        result=updater.update_category('electricity')
        self.assertEqual(result['sources'][0]['status'],'error')
        self.assertEqual(self.store.updates()[0]['status'],'error')
        self.assertEqual(len(self.store.prices(include_test=True)),4)
        self.assertTrue(self.store.prices(include_test=True)[0]['is_stale'])

    def test_same_category_mutex_across_store_instances(self):
        with self.store.connect() as con:con.execute("UPDATE sources SET adapter='csv' WHERE id='test_power'")
        started=threading.Event();release=threading.Event();calls=[]
        def blocked(source):
            calls.append(source['id']);started.set();release.wait(5)
            return [PriceInput.model_validate(fixture('electricity',10,'kWh','test_power'))],b'TEST'
        updater=Updater(self.store,blocked)
        thread=threading.Thread(target=lambda:updater.update_category('electricity'))
        thread.start()
        try:
            self.assertTrue(started.wait(3))
            other=Updater(Store(self.store.path),blocked).update_category('electricity')
            self.assertEqual(other['status'],'already_running')
            self.assertEqual(len(calls),1)
        finally:release.set();thread.join(5)
        self.assertFalse(thread.is_alive())

    def test_csv_batch_is_atomic_on_invalid_source(self):
        with self.assertRaises(ValueError):self.store.import_prices([fixture(),{**fixture(),'source_id':'missing'}])
        self.assertEqual(self.store.prices(include_test=True),[])

    def test_csv_roundtrip(self):
        f=fixture();buffer=io.StringIO();writer=csv.DictWriter(buffer,fieldnames=list(f));writer.writeheader();writer.writerow(f)
        result=self.store.import_prices(parse_csv(buffer.getvalue()))
        self.assertEqual(result['inserted'],1)

    def test_official_parser_schema_dates_and_test_label(self):
        # TEST document, not downloaded data and never imported as a real price.
        html='<p>С 1 января 2020 года для небытовых нужд действуют следующие тарифы: 99,00 тенге с НДС 90,00 тенге без НДС за 1 кВт.ч Потребители, использующие электрическую энергию не для бытовых нужд (2 группа)</p>'
        source={'id':'test_power','url':'https://www.esalmaty.kz/ru/business-tariffs','config':{'test_mode':True}}
        parsed=parse_esalmaty(html.encode(),source)
        self.assertEqual(str(parsed[0].value),'99.00')
        self.assertEqual(parsed[0].effective_from.isoformat(),'2020-01-01')
        self.assertIsNone(parsed[0].published_at)
        self.assertTrue(parsed[0].is_test);self.assertEqual(parsed[0].reliability,'test')
        with self.assertRaises(SourceError):parse_esalmaty(b'<p>TEST changed layout</p>',source)

    def test_csv_adapter_download_and_validation_path(self):
        from src.market.adapters import fetch_source
        f=fixture('electricity',10,'kWh','test_power');buffer=io.StringIO();writer=csv.DictWriter(buffer,fieldnames=list(f));writer.writeheader();writer.writerow(f)
        with patch('src.market.adapters.public_get',return_value=buffer.getvalue().encode()) as network:
            rows,payload=fetch_source({'id':'test_power','url':'https://example.invalid/TEST.csv','adapter':'csv','config':{}})
        network.assert_called_once();self.assertTrue(rows[0].is_test)
        self.assertEqual(self.store.import_prices(rows)['inserted'],1)

    def test_history_changes_stay_in_same_series(self):
        self.store.import_prices([fixture(),{**fixture(value=4),'published_at':'2020-02-01','effective_from':'2020-02-01'}])
        changes=price_changes(self.store.prices(include_test=True))
        self.assertEqual(changes[0]['percent_change'],100)
        self.assertEqual(changes[0]['observations'],2)

    def test_scenarios_actual_arithmetic_no_double_counting(self):
        self.populated()
        from src.market import scenarios
        original=scenarios.calculate_profitability
        with patch.object(scenarios,'calculate_profitability',wraps=original) as spy:
            result=compare(self.store,scenario_input())
        rows={r['scenario']:r for r in result['scenarios']}
        self.assertEqual([rows[k]['net_profit'] for k in 'ABCD'],[38,140,240,-40])
        self.assertEqual(rows['B']['revenue'],200)
        self.assertEqual(rows['C']['revenue'],300)
        self.assertEqual(rows['D']['revenue'],10)
        spy.assert_called_once()
        self.assertEqual(rows['C']['legacy_profitability_reconciliation']['processing_net_profit'],240)
        self.assertEqual(result['recommended_scenario'],'C')
        self.assertEqual(result['recommendation_scope'],'test_or_stale_price_scenario_only')
        self.assertAlmostEqual(rows['B']['break_even_price_to_match_sale'],78/18)
        self.assertAlmostEqual(rows['C']['break_even_price_to_match_sale'],9.8)
        sensitivity=next(r for r in result['sensitivity'] if r['scenario']=='B')
        self.assertEqual(sensitivity['net_profit_plus_20pct'],176)
        self.assertEqual(len(self.store.scenarios()),1)

    def test_ineligible_gas_and_digestate_never_credited(self):
        self.populated()
        result=compare(self.store,{**scenario_input(),'gas_sale_legal_confirmed':False,'digestate_quality_confirmed':False})
        rows={r['scenario']:r for r in result['scenarios']}
        self.assertEqual(rows['C']['status'],'ineligible');self.assertIsNone(rows['C']['net_profit'])
        self.assertEqual(rows['D']['status'],'ineligible');self.assertEqual(result['recommended_scenario'],'B')

    def test_missing_inputs_no_final_recommendation(self):
        result=compare(self.store,{'region':'KZ-TEST','mass_kg':20})
        self.assertEqual(result['status'],'needs_input')
        self.assertIsNone(result['recommended_scenario'])
        self.assertTrue(all(r['net_profit'] is None for r in result['scenarios']))

    def test_natural_gas_cannot_value_raw_biogas(self):
        self.populated();identifier=self.store.import_prices([fixture('natural_gas',80,'m3','test_gas')])['ids'][0]
        result=compare(self.store,{**scenario_input(),'price_ids':{'gas_sale':identifier}})
        self.assertEqual(result['scenarios'][2]['status'],'needs_input')
        with self.assertRaises(ValueError):ScenarioInput.model_validate({**scenario_input(),'gas_sale_product':'natural_gas'})

    def test_fertilizer_not_a_direct_digestate_price(self):
        self.populated();identifier=self.store.import_prices([fixture('urea',500,'kg','test_mineral')])['ids'][0]
        result=compare(self.store,{**scenario_input(),'price_ids':{'digestate':identifier}})
        self.assertEqual(result['scenarios'][3]['status'],'needs_input')

    def test_region_currency_tax_and_gas_basis_checked(self):
        self.populated()
        for updates in [{'region':'KZ-OTHER'},{'currency':'USD'},{'tax_basis':'VAT_excluded'}]:
            self.assertTrue(all(r['status']=='needs_input' for r in compare(self.store,{**scenario_input(),**updates})['scenarios']))
        result=compare(self.store,{**scenario_input(),'gas_volume_basis':'different'})
        self.assertEqual(result['scenarios'][2]['status'],'needs_input')

    def test_no_implicit_test_prices_in_production_comparison(self):
        self.populated()
        result=compare(self.store,{**scenario_input(),'allow_test_prices':False})
        self.assertIsNone(result['recommended_scenario'])
        self.assertEqual(result['selected_prices'],{})

    def test_boolean_numbers_and_nonfinite_rejected(self):
        for update in [{'mass_kg':True},{'mass_kg':float('inf')},{'vs_mass_kg':21}]:
            with self.assertRaises(ValueError):ScenarioInput.model_validate({**scenario_input(),**update})

    def test_agent_calls_market_and_bmp_tools_with_missing_food_waste_data(self):
        self.populated()
        agent=Agent(context={'market_region':'KZ-TEST'},llm=HybridLLM(providers=[]),registry=ToolRegistry(self.store))
        reply=agent.ask('У меня 20 кг пищевых отходов. Что выгоднее: продать или переработать в биогаз?')
        results={r['tool']:r['result'] for r in reply['tools']}
        self.assertIn('get_market_prices',results);self.assertIn('compare_market_scenarios',results)
        self.assertFalse(results['predict_bmp']['model_called'])
        self.assertIsNone(results['compare_market_scenarios']['recommended_scenario'])
        self.assertEqual(results['get_market_prices']['prices'],[]) # test records never become live market data

    def test_economic_question_retrieves_all_roles_not_only_word_biogas(self):
        actual={**fixture('electricity',10,'kWh','test_power'),'is_test':False,'reliability':'verified_manual'}
        self.store.import_prices([actual])
        agent=Agent(context={'market_region':'KZ-TEST'},llm=HybridLLM(providers=[]),registry=ToolRegistry(self.store))
        reply=agent.ask('20 кг пищевых отходов: выгоднее продать или переработать в биогаз?')
        result=next(t['result'] for t in reply['tools'] if t['tool']=='get_market_prices')
        self.assertEqual(result['prices'][0]['commodity'],'electricity')

    def test_fastapi_imports_validation_and_defaults(self):
        with TestClient(create_app(self.store,scheduler_enabled=False)) as client:
            self.assertEqual(client.get('/health').status_code,200)
            response=client.post('/prices',json=fixture())
            self.assertEqual(response.status_code,201)
            self.assertEqual(client.post('/prices',json=fixture()).json()['duplicates'],1)
            self.assertEqual(client.get('/prices/current').json()['prices'],[])
            self.assertEqual(client.post('/prices',json={**fixture(),'unit':'kWh'}).status_code,422)
            self.assertEqual(client.get('/prices/history?commodity=food_waste&region=KZ-TEST&start=bad').status_code,422)
            self.assertEqual(client.post('/updates?category=bad').status_code,422)
            self.assertEqual(client.post('/sources',json={},headers={'Origin':'https://foreign.invalid'}).status_code,403)
            self.assertEqual(client.post('/scenarios/compare',json={'mass_kg':20}).json()['status'],'needs_input')

    def test_scheduler_runs_once_and_stops_cleanly(self):
        async def test():
            stop=asyncio.Event();loop=asyncio.get_running_loop();calls=[]
            class Fake:
                def update_all(self):calls.append(True);loop.call_soon_threadsafe(stop.set)
            await scheduler(Fake(),stop,86400)
            self.assertEqual(len(calls),1)
        asyncio.run(test())


if __name__=='__main__':unittest.main()
