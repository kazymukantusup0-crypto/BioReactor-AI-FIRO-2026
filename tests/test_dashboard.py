"""Dashboard integration, isolated DBs; no fictitious production observations."""
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
import socket
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import main
from fastapi.testclient import TestClient
from src.data.prepare import ROOT
from src.market.store import Store
from src.market.api import create_app
from src.agent.providers import ProviderError
from src.dashboard.schemas import MeasurementContract


class DashboardTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.store=Store(Path(temp.name)/'dashboard_test.sqlite3')
        self.client=TestClient(create_app(self.store,scheduler_enabled=False))
        self.client.__enter__();self.addCleanup(self.client.__exit__,None,None,None)

    def session(self,mode='no_llm'):
        response=self.client.post('/api/dashboard/chat/sessions',json={'mode':mode,'context':{'market_region':'KZ-Karaganda'}})
        self.assertEqual(response.status_code,201);return response.json()['id']

    def test_schema_matches_trusted_artifact_and_diagnostic_roles(self):
        for name,path in [('stage1','models/metadata.json'),('stage1_5','models/stage1_5/metadata.json')]:
            meta=json.loads((ROOT/path).read_text(encoding='utf-8'))
            schema=self.client.get(f'/api/dashboard/models/{name}/schema').json()
            self.assertEqual([f['name'] for f in schema['fields']],meta['schema']['features'])
            self.assertEqual(schema['version'],meta['model_version'])
            self.assertEqual([f['name'] for f in schema['fields'] if f['role']=='prediction'],meta['schema'].get('prediction_features',meta['schema']['features']))
            self.assertNotIn('temperature_c',[f['name'] for f in schema['fields']])
        self.assertEqual(self.client.get('/api/dashboard/models/arbitrary/schema').status_code,404)

    def test_predict_loads_both_preserved_estimators_without_training(self):
        context=json.loads((ROOT/'examples/stage1_5_measured.json').read_text(encoding='utf-8'))
        for name in ['stage1','stage1_5']:
            response=self.client.post('/api/dashboard/predict',json={'model':name,'context':context})
            self.assertEqual(response.status_code,200);result=response.json()
            self.assertEqual(result['status'],'ok');self.assertTrue(result['model_called'])
            self.assertGreater(result['bmp'],0);self.assertIsNone(result['uncertainty']['interval_90'])
            self.assertIn('model_version',result)
        with self.store.connect() as con:self.assertEqual(con.execute('SELECT count(*) FROM dashboard_predictions').fetchone()[0],2)

    def test_unsupported_feedstock_never_returns_fictional_bmp(self):
        result=self.client.post('/api/dashboard/predict',json={'context':{'material':'food_waste','mass_kg':5,'reactor_volume_l':90}}).json()
        self.assertNotEqual(result['status'],'ok');self.assertFalse(result['model_called']);self.assertNotIn('bmp',result)

    def test_bad_prediction_context_rejected_at_api_boundary(self):
        for context in [{'mass_kg':True},{'mass_kg':-1},{'temperature_c':-300},{'arbitrary_code':'TEST'}]:
            self.assertEqual(self.client.post('/api/dashboard/predict',json={'context':context}).status_code,422)
        self.assertEqual(self.client.post('/api/dashboard/predict',json={'model':'../../etc','context':{}}).status_code,422)

    def test_real_scientific_reports_separate_cv_from_final_test(self):
        response=self.client.get('/api/dashboard/scientific');self.assertEqual(response.status_code,200)
        data=response.json()
        self.assertEqual(data['dataset']['raw_rows'],619);self.assertEqual(data['dataset']['clean_rows'],613)
        self.assertEqual(data['dataset']['laboratories'],31)
        self.assertEqual(data['stage1']['test']['n'],109);self.assertIsNone(data['stage1_5']['test'])
        self.assertAlmostEqual(data['stage1_5']['nested_cv']['macro_lab_MAE'],53.91675868361973)
        self.assertEqual(len(data['nested_cv_comparison']),8)
        self.assertIn('не независимая',data['evaluation_notice'])

    def test_figures_are_allowlisted_and_png(self):
        response=self.client.get('/api/dashboard/scientific/figures/stage1_test_errors')
        self.assertEqual(response.status_code,200);self.assertTrue(response.content.startswith(b'\x89PNG'))
        self.assertEqual(self.client.get('/api/dashboard/scientific/figures/not_allowlisted').status_code,404)

    def test_local_chat_real_tools_and_idempotent_submission(self):
        ident=self.session();body={'message':'5 кг пищевых отходов, реактор объёмом 90 литров: выгодно ли переработать?','request_id':'TEST_request_001'}
        response=self.client.post(f'/api/dashboard/chat/sessions/{ident}/messages',json=body)
        self.assertEqual(response.status_code,200);reply=response.json()
        self.assertEqual(reply['mode'],'deterministic_tools_no_llm')
        results={t['tool']:t['result'] for t in reply['tools']}
        self.assertIn('compare_market_scenarios',results);self.assertFalse(results['predict_bmp']['model_called'])
        self.assertIsNone(results['compare_market_scenarios']['final_recommendation'])
        replay=self.client.post(f'/api/dashboard/chat/sessions/{ident}/messages',json=body)
        self.assertEqual(reply,replay.json())
        history=self.client.get(f'/api/dashboard/chat/sessions/{ident}').json()
        self.assertEqual(len(history['turns']),1);self.assertEqual(history['context']['mass_kg'],5)
        self.assertEqual(history['context']['reactor_volume_l'],90)
        self.assertEqual(len(self.store.scenarios()),1)

    def test_session_history_persists_across_app_instances(self):
        ident=self.session();body={'message':'Какая точность модели BMP?','request_id':'TEST_persist_001'}
        self.client.post(f'/api/dashboard/chat/sessions/{ident}/messages',json=body)
        with TestClient(create_app(Store(self.store.path),scheduler_enabled=False)) as second:
            data=second.get(f'/api/dashboard/chat/sessions/{ident}').json()
            self.assertEqual(data['turns'][0]['question'],body['message']);self.assertIsNotNone(data['turns'][0]['reply'])

    def test_unavailable_ollama_falls_back_with_explicit_status(self):
        ident=self.session('offline')
        with patch('src.agent.providers.JSONProvider.plan',side_effect=ProviderError('TEST Ollama unavailable')):
            response=self.client.post(f'/api/dashboard/chat/sessions/{ident}/messages',json={'message':'5 кг пищевых отходов: сколько метана?','request_id':'TEST_offline_001'})
        data=response.json();self.assertEqual(response.status_code,200)
        self.assertEqual(data['mode'],'deterministic_tools_no_llm');self.assertTrue(data['tools'])
        self.assertEqual(data['provider_status'][0]['status'],'unavailable_or_incompatible')
        self.assertIn('LLM не используется',data['answer'])

    def test_no_same_session_concurrency_or_request_id_reuse(self):
        ident=self.session();lease='dashboard-chat:'+ident;owner=self.store.acquire(lease)
        body={'message':'Какая точность модели?','request_id':'TEST_same_id_001'}
        self.assertEqual(self.client.post(f'/api/dashboard/chat/sessions/{ident}/messages',json=body).status_code,409)
        self.store.release(lease,owner)
        self.assertEqual(self.client.post(f'/api/dashboard/chat/sessions/{ident}/messages',json=body).status_code,200)
        self.assertEqual(self.client.post(f'/api/dashboard/chat/sessions/{ident}/messages',json={**body,'message':'Другой запрос'}).status_code,409)

    def test_chat_validates_unknown_sessions_modes_and_context(self):
        self.assertEqual(self.client.get('/api/dashboard/chat/sessions/unknown').status_code,404)
        self.assertEqual(self.client.post('/api/dashboard/chat/sessions',json={'mode':'external_auto'}).status_code,422)
        self.assertEqual(self.client.post('/api/dashboard/chat/sessions',json={'context':{'unknown':'TEST'}}).status_code,422)
        ident=self.session()
        for message in ['', ' ', 'x'*12001]:
            self.assertEqual(self.client.post(f'/api/dashboard/chat/sessions/{ident}/messages',json={'message':message,'request_id':'TEST_invalid_001'}).status_code,422)

    def test_no_fabricated_sensor_history_or_control_routes(self):
        data=self.client.get('/api/dashboard/reactor').json()
        self.assertFalse(data['connected']);self.assertIsNone(data['readings']);self.assertEqual(data['history'],[])
        self.assertFalse(data['actuator_access']);self.assertFalse(data['commands_enabled'])
        self.assertEqual(data['label'],'SIMULATION / NO LIVE SENSOR DATA')
        self.assertEqual(self.client.post('/api/dashboard/reactor/commands',json={'pump':'on'}).status_code,404)

    def test_mq_contract_cannot_claim_quantitative_methane(self):
        base={'device_id':'TEST_ONLY','measured_at':datetime.now(timezone.utc),'gas_instrument':'MQ_raw','mq_raw_adc':300}
        self.assertEqual(MeasurementContract.model_validate(base).mq_raw_adc,300)
        for values in [{'methane_fraction':.6},{'gas_volume_m3':1},{'gas_flow_m3_h':.1}]:
            with self.assertRaises(ValueError):MeasurementContract.model_validate({**base,**values})
        with self.assertRaises(ValueError):MeasurementContract.model_validate({**base,'measured_at':'2020-01-01T12:00:00'})
        with self.assertRaises(ValueError):MeasurementContract.model_validate({**base,'ph':15})

    def test_calibrated_gas_contract_needs_basis_and_composition_analyzer(self):
        base={'device_id':'TEST_ONLY','measured_at':datetime.now(timezone.utc),'gas_volume_m3':1,'gas_instrument':'calibrated_meter','calibration_reference':'TEST calibration'}
        with self.assertRaises(ValueError):MeasurementContract.model_validate(base)
        valid={**base,'gas_volume_basis':'TEST stated reference conditions'}
        self.assertEqual(MeasurementContract.model_validate(valid).gas_volume_m3,1)
        with self.assertRaises(ValueError):MeasurementContract.model_validate({**valid,'methane_fraction':.5})
        self.assertEqual(MeasurementContract.model_validate({**valid,'gas_instrument':'calibrated_analyzer','methane_fraction':.5}).methane_fraction,.5)

    def test_contract_is_documented_but_ingestion_is_disabled(self):
        data=self.client.get('/api/dashboard/reactor/contract').json()
        self.assertFalse(data['ingestion_enabled']);self.assertFalse(data['commands_enabled'])
        self.assertIn('temperature_c',data['schema']['properties']);self.assertIn('gas_volume_basis',data['schema']['properties'])

    def test_diagnostics_checks_models_and_fails_honestly_for_ollama(self):
        with patch('src.dashboard.service.urllib.request.urlopen',side_effect=OSError('TEST unavailable')):
            data=self.client.get('/api/dashboard/status').json()
        self.assertEqual(data['sqlite']['status'],'ok');self.assertFalse(data['ollama']['available'])
        self.assertFalse(data['ollama']['generation_checked']);self.assertTrue(all(m['available'] for m in data['models']))
        self.assertEqual(data['network_mode'],'local');self.assertEqual(data['internet_connection'],'not_probed')
        self.assertNotIn('key',json.dumps(data).lower())

    def test_overview_has_null_unmeasured_values(self):
        with patch('src.dashboard.service.ollama_status',return_value={'available':False}):
            data=self.client.get('/api/dashboard/overview').json()
        self.assertIsNone(data['latest_prediction']);self.assertIsNone(data['latest_economics'])
        self.assertEqual(data['sensor_history'],[]);self.assertIsNone(data['reactor']['readings'])

    def test_firo_demo_is_recorded_and_uses_existing_artifacts(self):
        data=self.client.get('/api/dashboard/demo').json()
        self.assertEqual(data['label'],'RECORDED DEMO')
        original=json.loads((ROOT/'reports/stage3_5/actual_agent_dialogue.json').read_text(encoding='utf-8'))
        self.assertEqual(data['transcript'],original);self.assertIn('не измерения вашей партии',data['example_notice'])

    def test_economic_schema_exposes_existing_parameters_without_test_mode(self):
        data=self.client.get('/api/dashboard/economics/schema').json()
        names=[f['name'] for fields in data['groups'].values() for f in fields]
        for name in ['vs_mass_kg','gas_cleaning_cost','gas_sale_legal_confirmed','digestate_quality_confirmed','allow_stale_prices']:self.assertIn(name,names)
        self.assertNotIn('allow_test_prices',names)
        result=self.client.post('/scenarios/compare',json={'region':'KZ-Karaganda','mass_kg':5}).json()
        self.assertIsNone(result['final_recommendation']);self.assertEqual(len(result['scenarios']),4)

    def test_static_dashboard_and_legacy_market_routes_coexist(self):
        response=self.client.get('/dashboard/')
        self.assertEqual(response.status_code,200);self.assertIn('BioReactor AI',response.text)
        self.assertEqual(self.client.get('/health').status_code,200)
        self.assertEqual(self.client.get('/prices/current').status_code,200)
        self.assertEqual(self.client.get('/api/dashboard/overview',headers={'Origin':'https://unrelated.invalid'}).status_code,403)

    def test_launcher_rejects_invalid_or_occupied_port_without_opening_browser(self):
        from src.dashboard.launcher import run
        with patch('src.dashboard.launcher.webbrowser.open') as opened:
            with self.assertRaisesRegex(ValueError,'between'):run(SimpleNamespace(port=-1,no_browser=False,no_scheduler=True))
            with socket.socket() as used:
                used.bind(('127.0.0.1',0));used.listen(1)
                with self.assertRaisesRegex(ValueError,'already in use'):run(SimpleNamespace(port=used.getsockname()[1],no_browser=False,no_scheduler=True))
            opened.assert_not_called()


if __name__=='__main__':unittest.main()
