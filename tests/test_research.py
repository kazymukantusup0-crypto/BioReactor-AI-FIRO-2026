"""Scientific contracts: units, source comparability, offline history and no invented income."""
import main
import copy,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from src.market.store import Store
from src.market.api import create_app
from src.market.adapters import SourceError
from src.estimation.schemas import EstimateRequest
from src.estimation.methane_potential import estimate
from src.estimation.unit_conversion import methane_l,volatile_mass
from src.research.evidence_extractor import catalog,validate_profile
from src.research.evidence_store import EvidenceStore
from src.research.research_cache import ResearchCache
from src.research.market_search import parse_manure,search as market_search
from src.research.source_validator import validate_url
from src.research.scientific_search import search as scientific_search
from src.research.orchestrator import research_and_estimate
from src.agent.conversation import ConversationAgent
from src.agent.providers import HybridLLM
from src.agent.tools import ToolRegistry

class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'isolated.sqlite3');self.evidence=EvidenceStore(self.store)
        self.cat=catalog()
        self.env=patch.dict(os.environ,{'BIOREACTOR_RESEARCH_ONLINE':'0'});self.env.start();self.addCleanup(self.env.stop)
    def calc(self,**changes):
        return estimate(EstimateRequest(volume_l=142,**changes),self.cat['profiles'],self.cat['energy_reference'])
    def fixture(self):
        # Explicit synthetic TEST HTML only for parser contract; never imported into production prices.
        return '<h1>Коровий навоз</h1><p>Караганда</p><p>≈700 ₸/тонна</p>'.encode()
    def test_dimensional_conversion(self):
        self.assertEqual(methane_l(2,300),600)
        self.assertAlmostEqual(volatile_mass(100,.1,.8),8)
    def test_real_profile_142_l_coarse_range(self):
        r=self.calc();self.assertEqual(r['result_level'],'HYPOTHETICAL_SCENARIO')
        self.assertAlmostEqual(r['wet_mass_kg']['low'],143.846)
        self.assertAlmostEqual(r['methane_potential_m3']['low'],2.92295072)
        self.assertAlmostEqual(r['methane_potential_m3']['high'],4.1139956)
        self.assertIsNone(r['raw_biogas_m3']);self.assertIsNone(r['net_profit'])
    def test_confirmed_comparable_form(self):self.assertEqual(self.calc(material_state='slurry')['result_level'],'LITERATURE_ESTIMATE')
    def test_dry_compost_and_bedded_are_incompatible(self):
        for state in ['dry','compost','bedded','fresh_solid']:
            with self.subTest(state=state):self.assertIsNone(self.calc(material_state=state)['methane_potential_m3'])
    def test_other_species_not_silently_pooled(self):self.assertIsNone(self.calc(material='swine_manure')['methane_potential_m3'])
    def test_all_measured_inputs_independent_of_profile(self):
        r=self.calc(material='swine_manure',density_kg_l=1,vs_mass_kg=10,bmp_ml_g_vs=250,gas_reference='dry STP')
        self.assertEqual(r['result_level'],'MEASURED');self.assertEqual(r['methane_potential_l'],{'low':2500,'high':2500})
    def test_partial_measured_solids_not_overwritten(self):self.assertIsNone(self.calc(ts_fraction=.05)['methane_potential_m3'])
    def test_wet_vs_not_multiplied_by_ts_again(self):
        r=self.calc(density_kg_l=1,ts_fraction=.2,vs_fraction_wet=.1,bmp_ml_g_vs=300,gas_reference='test reference')
        self.assertAlmostEqual(r['methane_potential_l']['low'],4260)
    def test_biogas_requires_methane_fraction(self):
        r=self.calc(methane_fraction=.6);self.assertAlmostEqual(r['raw_biogas_m3']['low'],r['methane_potential_m3']['low']/.6)
    def test_conflicting_mass_basis_rejected(self):
        with self.assertRaises(ValueError):EstimateRequest(ts_fraction=.1,vs_fraction_wet=.2)
        with self.assertRaises(ValueError):EstimateRequest(mass_kg=1,volume_l=2,density_kg_l=1)
    def test_unreviewed_and_bad_units_rejected(self):
        p=copy.deepcopy(self.cat['profiles'][0]);p['source']['verification_status']='DRAFT'
        with self.assertRaises(ValueError):validate_profile(p)
        p=copy.deepcopy(self.cat['profiles'][0]);p['values']['vs_fraction_wet']['normalized_unit']='kg VS/kg TS'
        with self.assertRaises(ValueError):validate_profile(p)
    def test_no_validated_coverage_claim(self):
        r=self.calc();self.assertIn('No validated coverage',r['uncertainty_status']);self.assertNotIn('interval_90',r)
    def test_append_only_and_deduplication(self):
        identifier=self.evidence.append('test',{'is_test':True,'value':1})
        self.assertEqual(identifier,self.evidence.append('test',{'is_test':True,'value':1}))
        with self.assertRaises(Exception):
            with self.store.connect() as con:con.execute('DELETE FROM research_records')
    def test_public_allowlist_blocks_ssrf_and_credentials(self):
        for url in ['http://127.0.0.1/test','https://127.0.0.1/test','https://evil.test','https://x:secret@stroitaxi.kz/','https://stroitaxi.kz:444/']:
            with self.subTest(url=url),self.assertRaises(SourceError):validate_url(url)
    def test_market_undated_ask_never_current_or_bid(self):
        r=parse_manure(self.fixture());self.assertIsNone(r['published_at']);self.assertFalse(r['is_current'])
        self.assertEqual(r['price_type'],'seller_ask');self.assertEqual(r['normalized_value'],.7)
    def test_parser_rejects_changed_units_and_region(self):
        with self.assertRaises(SourceError):parse_manure(self.fixture().replace('тонна'.encode(),'кг'.encode()))
        with self.assertRaises(SourceError):parse_manure(self.fixture().replace('Караганда'.encode(),'Алматы'.encode()))
    def test_offline_stale_cache_preserves_original_age(self):
        market_search(self.evidence,'cattle_manure',online=True,fetcher=lambda _:self.fixture())
        with self.store.connect() as con:con.execute("UPDATE research_cache SET stored_at='2020-01-01T00:00:00+00:00'")
        def unavailable(_):raise SourceError('TEST no internet')
        r=market_search(self.evidence,'cattle_manure',online=True,fetcher=unavailable)
        self.assertTrue(r['stale']);self.assertGreater(r['cache_age_hours'],24);self.assertFalse(r['offers'][0]['is_current'])
        self.assertEqual(self.evidence.logs()[0]['status'],'unavailable')
    def test_offline_without_cache_no_fabricated_prices(self):self.assertEqual(market_search(self.evidence,'cattle_manure')['offers'],[])
    def test_source_error_backoff_avoids_repeated_requests(self):
        calls=[]
        def unavailable(url):calls.append(url);raise SourceError('TEST HTTP 429')
        scientific_search(self.evidence,'cattle_manure',online=True,fetcher=unavailable)
        r=scientific_search(self.evidence,'cattle_manure',online=True,fetcher=unavailable)
        self.assertEqual(len(calls),1);self.assertEqual(r['network_status'],'backoff_after_source_error')
        market_search(self.evidence,'cattle_manure',online=True,fetcher=unavailable)
        r=market_search(self.evidence,'cattle_manure',online=True,fetcher=unavailable)
        self.assertEqual(len(calls),2);self.assertEqual(r['status'],'backoff_after_source_error')
    def test_discovery_cannot_promote_numbers(self):
        raw=json.dumps({'message':{'items':[{'DOI':'TEST:metadata-only','title':['TEST discovery']} ]}}).encode()
        r=scientific_search(self.evidence,'swine_manure',online=True,fetcher=lambda _:raw)
        self.assertEqual(r['reviewed_profiles'],[]);self.assertIn('NOT_FOR_CALCULATION',r['discovered'][0]['verification_status'])
    def test_no_buyer_bid_no_net_income(self):
        r=research_and_estimate(self.store,EstimateRequest(volume_l=142,online=True),lambda url: self.fixture() if 'stroitaxi' in url else b'{"message":{"items":[]}}')
        self.assertAlmostEqual(r['catalog_reference_value_kzt']['low'],100.6922)
        self.assertIsNone(r['economic_comparison']['ranking']);self.assertIsNone(r['gas_sale_revenue'])
        with self.store.connect() as con:self.assertEqual(con.execute('SELECT count(*) FROM observations').fetchone()[0],0)
    def test_existing_profitability_calculator_used_only_with_explicit_prices(self):
        inputs={'sale_price_per_kg':1,'recovery_fraction':.5,'methane_price_per_m3':100,'preparation_cost':10,'heating_cost':20,'operating_cost':30,'currency':'KZT','price_date':'2026-10-29','price_gas_volume_basis':'273.2 K; 1.01325 bar'}
        r=research_and_estimate(self.store,EstimateRequest(volume_l=142,economic_inputs=inputs))
        economic=r['user_economic_scenario'];self.assertEqual(economic['status'],'ok')
        self.assertAlmostEqual(economic['endpoints'][0]['processing_net_profit'],2.92295072*.5*100-60)
        self.assertIsNone(economic['final_recommendation']);self.assertIsNone(r['net_profit'])
        inputs['price_gas_volume_basis']='different TEST gas reference'
        r=research_and_estimate(self.store,EstimateRequest(volume_l=142,economic_inputs=inputs))
        self.assertEqual(r['user_economic_scenario']['status'],'invalid_input')
    def test_user_example_multiturn_does_not_pollute_facts(self):
        agent=ConversationAgent(llm=HybridLLM(providers=[]),registry=ToolRegistry(self.store),research_enabled=True)
        with patch('src.agent.tools.predict_tool',side_effect=AssertionError('Hafner must not run')):
            first=agent.ask('У меня 142 литра коровьего навоза и реактор вместимостью 200 литров. Лучше продать или переработать?')
            second=agent.ask('Сколько сейчас стоит мой навоз и сколько денег можно выручить за газ?')
            third=agent.ask('Навозная жижа')
        self.assertEqual(first['conversation_version'],'7')
        # Keep asking for the physical form instead of silently treating
        # unspecified manure as slurry and attaching a profile to the batch.
        self.assertEqual(first['pending_question']['fields'],['physical_state'])
        self.assertEqual(second['pending_question']['fields'],['physical_state'])
        self.assertNotIn('estimate_advanced_gas',[tool['tool'] for tool in second['tools']])
        self.assertNotIn('2.92',second['answer'])
        self.assertEqual(third['technical_metadata']['research_result']['result_level'],'LITERATURE_ESTIMATE')
        self.assertEqual(agent.state.value('reactor_total_volume_l'),200)
        self.assertIsNone(agent.state.value('density_kg_l'));self.assertIsNone(agent.state.value('bmp_ml_ch4_g_vs'))
    def test_uncertain_and_negated_forms_never_become_confirmed(self):
        from src.agent.research_bridge import augment
        from src.agent.dialogue_types import DialogueState,Extraction
        for text in ['Не знаю, навозная жижа или сухой навоз','Если это навозная жижа','Это не навозная жижа']:
            extraction=augment(text,DialogueState(),Extraction())
            self.assertFalse(any(e.name=='material_state' and e.provenance=='USER_CONFIRMED' for e in extraction.entities))
        extraction=augment('Твёрдый навоз с подстилкой',DialogueState(),Extraction())
        self.assertEqual(extraction.entities[0].value,'bedded')
    def test_api_validation_history_and_legacy_session_upgrade(self):
        with TestClient(create_app(self.store,scheduler_enabled=False)) as client:
            r=client.post('/api/research/estimate',json={'volume_l':142,'online':False});self.assertEqual(r.status_code,200)
            self.assertEqual(len(client.get('/api/research/runs').json()['runs']),1)
            self.assertEqual(client.post('/api/research/estimate',json={'volume_l':-1}).status_code,422)
            s=client.post('/api/dashboard/chat/sessions',json={'mode':'no_llm','conversation_version':'5.6'}).json()
            old=client.post(f"/api/dashboard/chat/sessions/{s['id']}/messages",json={'request_id':'test-old-turn','message':'У меня 142 литра коровьего навоза. Сколько метана?'}).json()
            upgraded=client.post(f"/api/dashboard/chat/sessions/{s['id']}/research-upgrade").json()
            self.assertEqual(upgraded['conversation_version'],'7');self.assertEqual(upgraded['turns'][0]['reply'],old)
            self.assertEqual(client.post(f"/api/dashboard/chat/sessions/{s['id']}/upgrade").json()['conversation_version'],'7')

if __name__=='__main__':unittest.main()
