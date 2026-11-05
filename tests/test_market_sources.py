"""FICTITIOUS mathematical/document fixtures, isolated temporary databases only.

Tests that exercise verified-production selection explicitly use verified_manual
in a disposable database; they do not assert that those quotes exist in reality.
Real network evidence is generated separately by verify_stage3_5.py.
"""
from datetime import date,datetime,timezone,timedelta
import io
import json
from pathlib import Path
import ssl
import sys
import tempfile
import unittest
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import main
import openpyxl
from fastapi.testclient import TestClient
from src.market.adapters import public_get,SourceError
from src.market.api import create_app,manual_observation
from src.market.domain import PriceInput,normalize_price,market_today
from src.market.official import parse_bns_workbook,parse_krec,parse_karaganda,SOURCES
from src.market.service import price_changes,recommendation_change,get_market_prices
from src.market.scenarios import compare,select_price,ScenarioInput,PriceUnavailable
from src.market.store import Store
from src.market.tls import verified_context
from src.market.updater import Updater
from src.agent.orchestrator import Agent
from src.agent.providers import HybridLLM
from src.agent.tools import ToolRegistry
from test_market import fixture,scenario_input


def workbook(value=1234,gas=12.34,cover='Дата опубликования:09.02.2020',header='Караганда'):
    book=openpyxl.Workbook();book.active.title='Обложка';book.active.append([cover])
    sheet=book.create_sheet('3')
    sheet.append(['3. Цены и тарифы на отдельные виды платных услуг в Республике Казахстан в январе 2020 года'])
    sheet.append([None,'Республика Казахстан',header])
    sheet.append(['Газ, транспортируемый по распределительным сетям, природный, за 1 куб.метр',gas,gas])
    sheet.append(['Газ сжиженный в баллонах',999999,999999])
    sheet.append(['Электроэнергия, по тарифам первого уровня для населения, использующего электрические плиты, за 100 кВт.ч',value,value])
    sheet.append(['Электроэнергия, по тарифам второго уровня',999999,999999])
    output=io.BytesIO();book.save(output);book.close();return output.getvalue()


def bns(category):
    return dict(id='test_power' if category=='electricity' else 'test_gas',category=category,
        url='https://stat.gov.kz/TEST',config={'test_mode':True})


class TLSTests(unittest.TestCase):
    def test_native_or_system_context_checks_certificates_and_hostname(self):
        with patch.dict('os.environ',{},clear=True):ctx=verified_context()
        self.assertEqual(ctx.verify_mode,ssl.CERT_REQUIRED);self.assertTrue(ctx.check_hostname)

    def test_invalid_explicit_bundle_fails_without_fallback(self):
        with patch.dict('os.environ',{'BIOREACTOR_MARKET_CA_BUNDLE':'TEST_NONEXISTENT_CA.pem'}):
            with self.assertRaises(OSError):verified_context()

    def test_insecure_context_is_rejected(self):
        with patch.dict('os.environ',{},clear=True),patch('src.market.tls.sys.platform','linux'),patch('src.market.tls.ssl.create_default_context',return_value=Mock(verify_mode=ssl.CERT_NONE,check_hostname=False)):
            with self.assertRaises(RuntimeError):verified_context()

    def test_certificate_failure_does_not_retry_insecurely(self):
        opener=Mock();opener.open.side_effect=ssl.SSLCertVerificationError('TEST untrusted certificate')
        with patch('src.market.adapters.urllib.request.build_opener',return_value=opener) as build:
            with self.assertRaisesRegex(SourceError,'untrusted certificate'):public_get('https://example.invalid/TEST')
        self.assertEqual(opener.open.call_count,1)
        handler=build.call_args.args[1]
        self.assertTrue(handler._context.check_hostname);self.assertEqual(handler._context.verify_mode,ssl.CERT_REQUIRED)

    def test_plain_http_and_cross_origin_redirect_rejected(self):
        with self.assertRaises(SourceError):public_get('http://example.invalid/TEST')
        with patch('src.market.adapters.urllib.request.build_opener') as build:
            build.return_value.open.return_value.__enter__.return_value.read.return_value=b'TEST public content'
            public_get('https://example.invalid/TEST',check_robots=False)
        redirect=build.call_args.args[0]
        with self.assertRaises(SourceError):redirect.redirect_request(None,None,302,'',{},'https://other.invalid/TEST')


class ParserTests(unittest.TestCase):
    def test_bns_exact_rows_region_period_and_price_per_100kwh(self):
        rows=parse_bns_workbook(workbook(),bns('electricity'),'https://stat.gov.kz/TEST.xlsx')
        self.assertEqual(len(rows),2);p=rows[1]
        self.assertEqual(normalize_price(p.value,p.unit,p.commodity),('12.34','kWh'))
        self.assertEqual(p.region,'KZ-Karaganda');self.assertEqual(p.published_at,date(2020,2,9))
        self.assertEqual(p.period_start,date(2020,1,1));self.assertEqual(p.period_end,date(2020,1,31))
        self.assertEqual(p.price_type,'reference');self.assertTrue(p.is_test)
        self.assertEqual(p.acquisition_method,'https_xlsx')

    def test_natural_gas_not_lpg(self):
        rows=parse_bns_workbook(workbook(),bns('natural_gas'),'https://stat.gov.kz/TEST.xlsx')
        self.assertEqual(str(rows[0].value),'12.34');self.assertEqual(rows[0].commodity,'natural_gas')

    def test_missing_confidential_footnoted_values_rejected(self):
        for raw in ['...','1234²','1234 2)',None,float('inf')]:
            with self.subTest(raw=raw),self.assertRaises((SourceError,ValueError)):
                parse_bns_workbook(workbook(value=raw),bns('electricity'),'https://stat.gov.kz/TEST.xlsx')

    def test_missing_publication_region_and_malformed_zip_fail(self):
        for payload in [workbook(cover='TEST no publication'),workbook(header='Астана'),b'TEST not an XLSX']:
            with self.subTest(payload=len(payload)),self.assertRaises(Exception):
                parse_bns_workbook(payload,bns('electricity'),'https://stat.gov.kz/TEST.xlsx')

    def test_city_unknown_publication_never_fabricated(self):
        html='Цены на услуги розничной реализации электрической энергии с 1 января 2020 года (г. Караганда) потребители, использующие электрическую энергию не для бытовых нужд 10,00 11,00'
        source=dict(id='test_power',url='https://example.invalid/TEST',config={'test_mode':True})
        rows=parse_karaganda(html.encode(),source)
        self.assertIsNone(rows[0].published_at);self.assertTrue(rows[0].is_test)
        with self.assertRaises(SourceError):parse_karaganda(b'TEST changed layout',source)

    def test_krec_notice_correlated_and_districts_not_city(self):
        html='<span lang="kk">TEST unrelated text</span> Абайского, Бухар-Жырауского, Нуринского, Осакаровского и Каркаралинского районов ЦЕНЫ НА ЭЛЕКТРОСНАБЖЕНИЕ С 15.01.2020 Не для бытовых нужд 10,00 ₸/кВт С НДС (16%): 11,60'
        notice=b'<time datetime="2020-01-09">TEST</time><a href="/files/price_2020-01-15_notice.docx">TEST</a>'
        source=dict(id='test_power',url='https://example.invalid/TEST',config={'test_mode':True})
        rows=parse_krec(html.encode(),notice,source)
        self.assertEqual(len(rows),10);self.assertTrue(all(p.region.endswith('-district') and p.is_test for p in rows))
        self.assertEqual(rows[0].published_at,date(2020,1,9))
        with self.assertRaises(SourceError):parse_krec(html.encode(),b'TEST no notice',source)
        with self.assertRaises(SourceError):parse_krec(html.replace('Абайского','TEST').encode(),notice,source)


class MarketReliabilityTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.store=Store(Path(temp.name)/'TEST.sqlite3')
        for ident,category in [('test_feed','organic_feedstock'),('test_power','electricity'),('test_gas','natural_gas'),('test_fert','organic_fertilizer')]:
            self.store.add_source(dict(id=ident,name='FICTITIOUS TEST SOURCE',url='https://example.invalid/TEST',category=category))

    def quote(self,commodity='electricity',value=10,source_id='test_power',day=None):
        # Deliberately verified-shaped fixtures, exclusively in a temporary TEST DB.
        unit='kWh' if commodity=='electricity' else 'm3' if commodity=='raw_biogas' else 'kg'
        return {**fixture(commodity,value,unit,source_id,effective=(day or market_today()).isoformat()),'is_test':False,'reliability':'verified_manual'}

    def test_fresh_cache_becomes_unavailable_on_network_failure_and_recovers(self):
        self.store.import_prices([self.quote()])
        with self.store.connect() as con:con.execute("UPDATE sources SET adapter='csv' WHERE id='test_power'")
        fetch=Mock(side_effect=SourceError('TEST no internet'));updater=Updater(self.store,fetcher=fetch)
        updater.update_category('electricity')
        p=self.store.prices()[0]
        self.assertEqual(p['validation_status'],'UNAVAILABLE');self.assertFalse(p['usable_as_current'])
        self.assertEqual(p['age_days'],0);self.assertEqual(p['value'],'10')
        self.assertEqual(updater.update_category('electricity')['sources'][0]['status'],'rate_limited');fetch.assert_called_once()
        state=self.store.source_state('test_power')
        delay=datetime.fromisoformat(state['next_attempt_at'])-datetime.fromisoformat(state['last_attempt_at'])
        self.assertEqual(delay.total_seconds(),300)
        self.store.finish_source('test_power',True)
        self.assertEqual(self.store.prices()[0]['validation_status'],'VERIFIED_CURRENT')

    def test_backoff_bounded_and_automatic_empty_batch_is_failure(self):
        for n,delay in enumerate([300,600,1200,86400,86400],1):
            self.store.finish_source('test_power',False,error='TEST')
            s=self.store.source_state('test_power');self.assertEqual(s['consecutive_failures'],n)
            self.assertEqual((datetime.fromisoformat(s['next_attempt_at'])-datetime.fromisoformat(s['last_attempt_at'])).total_seconds(),delay)
        with self.store.connect() as con:
            con.execute("UPDATE sources SET adapter='csv' WHERE id='test_feed'")
        result=Updater(self.store,fetcher=lambda s:([],b'TEST empty')).update_category('organic_feedstock')
        self.assertEqual(result['sources'][0]['status'],'error')

    def test_manual_configuration_logged_daily_not_every_scheduler_tick(self):
        updater=Updater(self.store)
        self.assertEqual(updater.update_category('electricity')['sources'][0]['status'],'needs_configuration')
        self.assertEqual(updater.update_category('electricity')['sources'][0]['status'],'rate_limited')
        self.assertEqual(len(self.store.updates()),1)

    def test_all_five_validation_states(self):
        today=market_today()
        self.store.import_prices([self.quote(day=today-timedelta(days=40)),self.quote(value=11,day=today-timedelta(days=20)),self.quote(value=12)])
        states={p['validation_status'] for p in self.store.prices()}
        self.assertEqual(states,{'VERIFIED_HISTORICAL','VERIFIED_CURRENT'})
        stale={**self.quote(value=4,day=today-timedelta(days=40)),'consumer_class':'TEST_old_profile'}
        unknown={**self.quote(value=5),'consumer_class':'TEST_unknown','published_at':None}
        unverified={**self.quote(value=6),'consumer_class':'TEST_unverified','reliability':'unverified'}
        self.store.import_prices([stale,unknown,unverified])
        self.assertEqual({p['validation_status'] for p in self.store.prices()}, {'VERIFIED_CURRENT','VERIFIED_HISTORICAL','STALE','UNVERIFIED'})
        self.store.finish_source('test_power',False,error='TEST')
        self.assertIn('UNAVAILABLE',{p['validation_status'] for p in self.store.prices()})

    def test_invalid_currency_region_dates_method_and_units_rejected(self):
        for update in [{'currency':'ABC'},{'region':'RU-Karaganda'},{'unit':'kJ'},
            {'period_start':'2020-01-01'},{'acquisition_method':'invented'},
            {'published_at':(market_today()+timedelta(days=1)).isoformat()}]:
            with self.subTest(update=update),self.assertRaises(ValueError):PriceInput.model_validate({**self.quote(),**update})

    def test_manual_ingress_cannot_claim_automatic_official_acquisition(self):
        p=manual_observation(PriceInput.model_validate({**self.quote(),'reliability':'verified_official','acquisition_method':'https_xlsx'}))
        self.assertEqual(p.reliability,'verified_manual');self.assertEqual(p.acquisition_method,'manual')

    def test_period_unit_dedup_and_official_sources_no_test_flags(self):
        self.store.import_prices([self.quote(value=12.34)])
        p={**self.quote(value=1234),'unit':'100_kWh','acquisition_method':'https_xlsx'}
        self.assertEqual(self.store.import_prices([p])['duplicates'],1)
        self.assertTrue(all(not s.get('config',{}).get('test_mode') for s in SOURCES))

    def test_exact_7_30_90_day_changes_and_sparse_history(self):
        today=market_today()
        self.store.import_prices([self.quote(value=10,day=today-timedelta(days=n)) for n in [7,30,90]]+[self.quote(value=20)])
        changes=price_changes(self.store.prices(),as_of=today)[0]
        for n in ['7','30','90']:self.assertEqual(changes['windows_days'][n]['percent_change'],100)
        sparse=price_changes(self.store.prices(),as_of=today-timedelta(days=1))[0]
        self.assertTrue(all(p['status']=='insufficient_history' and p['percent_change'] is None for p in sparse['windows_days'].values()))

    def test_reference_national_prices_disclosed_but_not_used_in_local_profit(self):
        p={**self.quote(),'region':'KZ-national','price_type':'reference'}
        self.store.import_prices([p])
        reply=get_market_prices({'market_region':'KZ-Karaganda'},self.store)
        self.assertIn('общенациональные',reply['geographic_scope_warning'])
        for region in ['KZ-Karaganda','KZ-national']:
            with self.assertRaises(PriceUnavailable):select_price(self.store,ScenarioInput(region=region,tax_basis=p['tax_basis'],consumer_class=p['consumer_class']),'electricity')

    def test_verified_price_update_changes_recommendation_and_readonly_impact(self):
        yesterday=market_today()-timedelta(days=1)
        self.store.import_prices([self.quote('food_waste',2,'test_feed',yesterday),self.quote(day=yesterday)])
        data={**scenario_input(),'allow_test_prices':False,'gas_sale_legal_confirmed':False,'digestate_quality_confirmed':False}
        old=compare(self.store,data)
        self.assertEqual(old['final_recommendation'],'B')
        self.store.import_prices([self.quote('food_waste',20,'test_feed')])
        impact=recommendation_change(self.store,old['scenario_id'])
        self.assertEqual(impact['previous_recommendation'],'B');self.assertEqual(impact['current_recommendation'],'A')
        self.assertEqual(next(r['difference'] for r in impact['profit_changes'] if r['scenario']=='A'),360)
        self.assertEqual(len(self.store.scenarios()),1)
        self.assertEqual(self.store.scenarios()[0]['result_json']['recommended_scenario'],'B')
        with TestClient(create_app(self.store,scheduler_enabled=False)) as client:
            self.assertEqual(client.get(f"/scenarios/{old['scenario_id']}/price-impact").json()['current_recommendation'],'A')
            self.assertEqual(client.get('/scenarios/999999/price-impact').status_code,404)
            self.assertIn('states',client.get('/sources/status').json())

    def test_unverified_update_cannot_produce_final_recommendation(self):
        yesterday=market_today()-timedelta(days=1)
        self.store.import_prices([self.quote('food_waste',2,'test_feed',yesterday),self.quote(day=yesterday)])
        data={**scenario_input(),'allow_test_prices':False,'gas_sale_legal_confirmed':False,'digestate_quality_confirmed':False}
        old=compare(self.store,data)
        self.store.import_prices([{**self.quote('food_waste',20,'test_feed'),'reliability':'unverified'}])
        self.assertIsNone(recommendation_change(self.store,old['scenario_id'])['current_recommendation'])

    def test_agent_karaganda_region_and_provenance_no_hallucinated_profit(self):
        p={**self.quote(),'region':'KZ-Karaganda'};self.store.import_prices([p])
        agent=Agent(llm=HybridLLM(providers=[]),registry=ToolRegistry(self.store))
        reply=agent.ask('В Караганде 20 кг пищевых отходов: что выгоднее продать или переработать?')
        self.assertEqual(reply['context']['market_region'],'KZ-Karaganda')
        self.assertIn('example.invalid/TEST',reply['answer']);self.assertIn('FICTITIOUS TEST SOURCE',reply['answer'])
        result=next(t['result'] for t in reply['tools'] if t['tool']=='compare_market_scenarios')
        self.assertIsNone(result['final_recommendation'])
        self.assertIn('VERIFIED_CURRENT',reply['answer'])


if __name__=='__main__':unittest.main()
