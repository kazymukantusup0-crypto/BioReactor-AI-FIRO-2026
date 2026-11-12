"""MVP endpoint tests; no model is loaded by this module."""
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from src.market.api import create_app
from src.market.store import Store
from src.dashboard.firo_demo import build_result


@pytest.fixture
def demo(tmp_path):
    with TestClient(create_app(Store(tmp_path/'demo.sqlite3'),scheduler_enabled=False,firo_demo=True)) as client:yield client


def test_opt_in_required(tmp_path):
    with TestClient(create_app(Store(tmp_path/'ordinary.sqlite3'),scheduler_enabled=False)) as client:
        assert client.get('/api/dashboard/firo-demo/scenarios').json()['enabled'] is False
        assert client.post('/api/dashboard/firo-demo/runs',json={'case':'methane'}).status_code==409


def test_three_scenarios_need_no_model_and_survive_restore(demo):
    for case in ['methane','incomplete','oxygen']:
        with patch('src.agent.providers.JSONProvider.generate',side_effect=AssertionError('LLM must not run')):
            response=demo.post('/api/dashboard/firo-demo/runs',json={'case':case})
        assert response.status_code==201,response.text
        value=response.json()
        assert demo.get('/api/dashboard/firo-demo/runs/'+value['id']).json()==value
        assert value['explanation']['status']=='not_requested'
        assert value['input_notice'] and 'state' not in value
    methane=build_result('methane')
    assert methane['results'][0]['value']==150
    assert methane['results'][0]['provenance']=='CALCULATED'
    assert methane['verification']['arithmetic']['all_checks_passed'] is True
    assert methane['verification']['scientific']['status']=='passed'
    incomplete=build_result('incomplete')
    assert incomplete['verification']['capacity']['simultaneous_load_possible'] is None
    assert incomplete['verification']['capacity']['reactor_working_volume_l'] is None
    for key in ('density_kg_l','mass_kg','vs_mass_kg','bmp_ml_ch4_g_vs'):
        assert key not in incomplete['state']['facts'] and key not in incomplete['state']['derived']
    assert incomplete['results'][-1]['value'] is None and len(incomplete['questions'])==2
    oxygen=build_result('oxygen')
    assert 'CO₂' in oxygen['answer'] and 'Не все виды' in oxygen['answer']
    assert oxygen['verification']['scientific']['status']=='passed' and oxygen['sources']


def test_model_unavailable_does_not_erase_python_answer(demo):
    value=demo.post('/api/dashboard/firo-demo/runs',json={'case':'methane'}).json()
    with patch('src.dashboard.firo_demo.explain_with_qwen',return_value={'status':'unavailable','text':None,'message':'Модель недоступна'}):
        result=demo.post(f"/api/dashboard/firo-demo/runs/{value['id']}/explain").json()
    assert result['answer']==value['answer'] and result['results']==value['results']
    assert result['explanation']['status']=='unavailable'


def test_cancel_reaches_provider_and_late_explanation_cannot_replace_result(demo):
    value=demo.post('/api/dashboard/firo-demo/runs',json={'case':'methane'}).json()
    entered=threading.Event();release=threading.Event();signals=[]
    def late_answer(record,signal):
        signals.append(signal);entered.set();assert release.wait(5)
        return {'status':'accepted','text':'Late answer','message':'ok'}
    with patch('src.dashboard.firo_demo.explain_with_qwen',side_effect=late_answer),ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(demo.post,f"/api/dashboard/firo-demo/runs/{value['id']}/explain")
        assert entered.wait(5)
        cancelled=demo.post(f"/api/dashboard/firo-demo/runs/{value['id']}/cancel").json()
        assert cancelled['explanation']['status']=='cancelled' and signals[0].cancelled
        release.set();result=future.result(timeout=5).json()
    assert result['explanation']['status']=='cancelled' and result['explanation']['text'] is None
    assert result['results']==value['results']


def test_unknown_case_rejected(demo):
    assert demo.post('/api/dashboard/firo-demo/runs',json={'case':'invented'}).status_code==422


@pytest.mark.parametrize('text,expected',[
    ('Это расчётный потенциал, а не измеренная выработка. Для прогноза за срок нужна кинетика.','accepted'),
    ('Реактор произведёт 1500 л CH₄.','rejected'),
])
def test_optional_model_explanation_is_verified_before_display(text,expected):
    from evaluations import qwen4b_manual_chat as qa
    from src.dashboard.firo_demo import explain_with_qwen
    from src.agent.providers import JSONProvider
    from src.agent.cancellation import CancellationSignal
    class Memory:
        def low(self):return False
        def close(self):pass
    row={'free_ram_mib':7500,'commit':{'commit_headroom_mib':18000},'api_version':{'version':'test'},'running_models':[],
         'gpu':{'temperature_c':55,'vram_total_mib':8192,'vram_used_mib':600,'hw_thermal_slowdown':'Not Active','sw_thermal_slowdown':'Not Active'}}
    def generation(self,messages,schema):
        self.metrics.append({'done_reason':'stop','status':'ok','raw_public_response':text})
        return {'explanation':text}
    with patch.object(qa,'WindowsLowMemory',Memory),patch.object(qa.telemetry,'sample',return_value=row), \
         patch.object(qa,'active_ollama_connections',return_value=[]),patch.object(qa,'unload_target_if_uncontended',return_value={'status':'UNLOADED'}), \
         patch.object(JSONProvider,'generate',generation):
        result=explain_with_qwen(build_result('methane'),CancellationSignal())
    assert result['status']==expected,result
    assert result['text']==(text if expected=='accepted' else None)
    assert result['telemetry']['unload']['status']=='UNLOADED'
