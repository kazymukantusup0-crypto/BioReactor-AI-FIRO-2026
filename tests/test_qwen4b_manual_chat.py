"""Deterministic checks only: no live Ollama requests."""
from unittest.mock import patch
import tempfile
from pathlib import Path

import pytest
from evaluations.qwen4b_manual_chat import ManualProvider, check_loaded, safety_reasons
from evaluations.qwen3_4b_resource_policy import load_policy
from src.agent.providers import JSONProvider, ProviderError, HybridLLM
from src.agent.dialogue_types import NLUProposal
from src.market.api import create_app
from src.market.store import Store
from fastapi.testclient import TestClient
from test_scientific_question_routing import _run_job
import evaluations.qwen4b_manual_chat as manual


def model(context=4096):
    return {'name':'qwen3:4b-q4_K_M', 'context_length':context}


@pytest.mark.parametrize('models', [[], [model(2048)], [model(), {'name':'other'}], [{'name':'other','context_length':4096}]])
def test_rejects_missing_wrong_or_additional_model(models):
    with pytest.raises(ProviderError): check_loaded({'models':models})


def test_each_request_verifies_loaded_model_and_never_starts_on_failure():
    provider = ManualProvider([])
    with patch('evaluations.qwen4b_manual_chat.loaded_model', side_effect=ProviderError('not loaded')):
        with patch.object(JSONProvider, 'generate') as generation:
            with pytest.raises(ProviderError): provider.generate([{'role':'user','content':'BMP'}])
            generation.assert_not_called()
    assert provider.events[0]['status'] == 'error'


def test_loaded_provider_uses_real_base_provider_and_preserves_keepalive():
    provider = ManualProvider([])
    with patch('evaluations.qwen4b_manual_chat.loaded_model', return_value=model()):
        with patch.object(JSONProvider, 'generate', return_value={'ok':True}) as generation:
            assert provider.generate([{'role':'user','content':'BMP'}]) == {'ok':True}
            assert generation.call_count == 1
    payload = provider.payload([{'role':'user','content':'BMP'}])
    assert payload['model'] == 'qwen3:4b-q4_K_M'
    assert payload['options']['num_ctx'] == 4096
    assert payload['keep_alive'] == '5m'
    assert 'biochemical methane potential' in payload['messages'][0]['content']


def test_model_disappearance_after_request_discards_result():
    provider = ManualProvider([])
    with patch('evaluations.qwen4b_manual_chat.loaded_model', side_effect=[model(), ProviderError('model disappeared')]):
        with patch.object(JSONProvider, 'generate', return_value={'ok':True}):
            with pytest.raises(ProviderError, match='model disappeared'):
                provider.generate([{'role':'user','content':'BMP'}])
    assert provider.events[0]['status'] == 'error'


def test_model_identity_change_discards_result():
    provider = ManualProvider([])
    with patch('evaluations.qwen4b_manual_chat.loaded_model', side_effect=[{**model(),'digest':'a'},{**model(),'digest':'b'}]):
        with patch.object(JSONProvider, 'generate', return_value={'ok':True}):
            with pytest.raises(ProviderError, match='identity changed'):
                provider.generate([{'role':'user','content':'BMP'}])


def test_model_call_limit_blocks_before_network():
    provider = ManualProvider([{} for _ in range(6)])
    with patch('evaluations.qwen4b_manual_chat.loaded_model') as loaded:
        with pytest.raises(ProviderError, match='call limit'):
            provider.generate([{'role':'user','content':'BMP'}])
        loaded.assert_not_called()


def test_limited_provider_bounds_calls_and_preserves_calibrated_options():
    provider=manual.LimitedProvider([])
    payload=provider.payload([{'role':'user','content':'BMP'}])
    assert payload['options']['num_ctx']==4096 and payload['options']['num_batch']==32
    assert payload['options']['num_gpu']==-1 and payload['keep_alive']=='5m'
    with patch.object(manual.telemetry,'get_json',side_effect=[{'models':[]},{'models':[model()]},{'models':[model()]},{'models':[model()]}]), \
         patch.object(manual,'loaded_model',return_value=model()), \
         patch.object(JSONProvider,'generate',return_value={'ok':True}) as generate:
        assert provider.generate([{'role':'user','content':'one'}])=={'ok':True}
        assert provider.generate([{'role':'user','content':'two'}])=={'ok':True}
        assert provider.generate([{'role':'user','content':'three'}],{'properties':{'conclusion':{}}})=={'ok':True}
        assert provider.generate([{'role':'user','content':'four'}],{'properties':{'conclusion':{}}})=={'ok':True}
        with pytest.raises(ProviderError,match='four-call limit'):
            provider.generate([{'role':'user','content':'three'}])
        assert generate.call_count==4


def test_limited_provider_reserves_a_synthesis_call_before_extra_planning():
    provider=manual.LimitedProvider([{'token_limit':128},{'token_limit':150},{'token_limit':150}])
    with patch.object(manual.telemetry,'get_json',return_value={'models':[model()]}), \
         patch.object(JSONProvider,'generate') as generate:
        with pytest.raises(ProviderError,match='synthesis budget reserved'):
            provider.generate([{'role':'user','content':'select'}],{'properties':{'action':{}}})
        generate.assert_not_called()


def test_limited_provider_does_not_reload_after_disappearance():
    provider=manual.LimitedProvider([{'status':'ok'}])
    with patch.object(manual.telemetry,'get_json',return_value={'models':[]}), \
         patch.object(JSONProvider,'generate') as generate:
        with pytest.raises(ProviderError,match='refusing reload'):
            provider.generate([{'role':'user','content':'next'}])
        generate.assert_not_called()


def test_existing_resource_policy_remains_fail_closed():
    row = {'free_ram_mib':7000,'commit':{'commit_headroom_mib':20000},'api_version':{'version':'0.40.16'},
           'running_models':[model()],'gpu':{'temperature_c':55,'vram_total_mib':8192,'vram_used_mib':3800,
           'hw_thermal_slowdown':'Not Active','sw_thermal_slowdown':'Not Active'}}
    problems = safety_reasons(row, load_policy(), admission=True)
    assert 'policy_not_admitted' in problems
    assert 'manual_preloaded_mode_not_admitted' in problems


def test_scientific_cases_keep_resource_admission_and_never_start_when_blocked(tmp_path):
    import json
    class Memory:
        def low(self): return False
        def close(self): pass
    row = {'free_ram_mib':6000,'commit':{'commit_headroom_mib':20000},'api_version':{'version':'0.40.16'},
           'running_models':[],'ollama_processes':[], 'gpu':{'temperature_c':55,'vram_total_mib':8192,'vram_used_mib':500,
           'hw_thermal_slowdown':'Not Active','sw_thermal_slowdown':'Not Active'}}
    assert len(manual.SCIENTIFIC_CASES['D']) == 2
    with patch.object(manual, 'ROOT', tmp_path), patch.object(manual, 'WindowsLowMemory', Memory), \
         patch.object(manual, 'active_ollama_connections', return_value=[]), \
         patch.object(manual.telemetry, 'sample', return_value=row), \
         patch.object(manual, 'create_app') as create:
        assert manual.limited_chat('D') == 2
        create.assert_not_called()
    trace=json.loads(next((tmp_path/'reports'/'qwen4b_manual_qa').glob('limited_chat_*.json')).read_text(encoding='utf-8'))
    assert trace['case']=='D' and trace['status']=='BLOCKED' and trace['limits']['admission_ram_mib']==6656
    assert not trace['provider_calls'] and not trace['turns']


def test_actual_chat_endpoint_uses_qa_provider_and_records_scientific_tool():
    calls = []
    def factory(*args, **kwargs):
        provider = ManualProvider(calls)
        provider.extract_dialogue = lambda *a, **k: NLUProposal(language='ru', intents=[], material=None, material_evidence=None, entities=[])
        provider.generate = lambda *a, **k: (_ for _ in ()).throw(ProviderError('deterministic test: no synthesis'))
        return HybridLLM('offline', providers=[provider], strict_model=True)
    with tempfile.TemporaryDirectory(dir=Path.cwd(), prefix='.tmp-manual-chat-test-') as tmp:
        app = create_app(Store(Path(tmp) / 'qa.sqlite3'), scheduler_enabled=False)
        with patch('src.dashboard.api.HybridLLM', side_effect=factory), TestClient(app) as client:
            _, _, reply = _run_job(client, 'Почему метаногенез проходит без кислорода?', 'TEST_MANUAL_CHAT')
            assert any(tool['tool'] == 'search_scientific_sources' for tool in reply['tools'])
            assert 'кислород' in reply['answer'].lower()


def test_requested_question_runs_through_actual_chat_endpoint():
    from test_scientific_question_routing import _fake_runtime_llm
    query='Объясни разницу между BMP, теоретическим максимальным выходом метана и фактическим выходом метана за 30 дней. Нужен ли кислород для метаногенеза?'
    with tempfile.TemporaryDirectory(dir=Path.cwd(), prefix='.tmp-manual-science-test-') as tmp:
        app=create_app(Store(Path(tmp)/'qa.sqlite3'), scheduler_enabled=False)
        with patch('src.dashboard.api.HybridLLM',side_effect=_fake_runtime_llm), TestClient(app) as client:
            _,_,reply=_run_job(client,query,'TEST_MANUAL_CONCEPTS')
            assert any(tool['tool']=='search_scientific_sources' for tool in reply['tools'])
            answer=reply['answer'].lower()
            assert 'кислород' in answer and 'кинетик' in answer and 'теоретическ' in answer
            assert not any(tool['tool']=='assess_substrate_potential' for tool in reply['tools'])


def test_calibration_stops_request_on_ram_limit_without_ollama(tmp_path):
    import time
    row = {'free_ram_mib':7000,'commit':{'commit_headroom_mib':20000},'api_version':{'version':'0.40.16'},
           'running_models':[],'gpu':{'temperature_c':55,'vram_total_mib':8192,'vram_used_mib':500,
           'hw_thermal_slowdown':'Not Active','sw_thermal_slowdown':'Not Active'}}
    bad = {**row, 'free_ram_mib':4000}
    class Memory:
        def low(self): return False
        def close(self): pass
    def fake_request(*args, **kwargs):
        signal=kwargs['cancellation']
        deadline=time.monotonic()+3
        while not signal.cancelled and time.monotonic()<deadline: time.sleep(.01)
        signal.throw_if_cancelled()
        raise AssertionError('cancellation was not delivered')
    with patch.object(manual, 'ROOT', tmp_path), patch.object(manual, 'WindowsLowMemory', Memory), \
         patch.object(manual, 'active_ollama_connections', return_value=[]), \
         patch.object(manual.telemetry, 'sample', side_effect=[row,bad,row]), \
         patch.object(manual.telemetry, 'get_json', return_value={'models':[]}), \
         patch.object(manual, 'request_json', side_effect=fake_request):
        assert manual.calibrate() == 1
    import json
    trace=json.loads(next((tmp_path/'reports'/'qwen4b_manual_qa').glob('calibration_*.json')).read_text(encoding='utf-8'))
    assert trace['status']=='INCOMPLETE'
    assert 'ram_limit' in trace['stop_reason']
    assert trace['worker_stopped'] is True
    assert trace['request_error'].startswith('ExecutionStopped')


def test_calibration_blocks_missing_telemetry_and_windows_pressure():
    assert 'telemetry_incomplete' in manual.calibration_issues({},False,admission=True)
    row={'free_ram_mib':7000,'commit':{'commit_headroom_mib':20000},'api_version':{'version':'x'},
         'running_models':[],'gpu':{'temperature_c':55,'vram_total_mib':8192,'vram_used_mib':500,
         'hw_thermal_slowdown':'Not Active','sw_thermal_slowdown':'Not Active'}}
    assert 'windows_low_memory_or_unknown' in manual.calibration_issues(row,True,admission=True)


def test_active_cancel_experiment_waits_for_stream_content_and_unloads(tmp_path):
    import json
    import threading
    import time
    row = {'free_ram_mib':7000,'commit':{'commit_headroom_mib':20000},'api_version':{'version':'0.40.16'},
           'running_models':[],'ollama_processes':[], 'gpu':{'temperature_c':55,'vram_total_mib':8192,'vram_used_mib':500,
           'hw_thermal_slowdown':'Not Active','sw_thermal_slowdown':'Not Active'}}
    ready=threading.Event(); count=[0]
    def sample(_):
        count[0]+=1
        if count[0]==2:
            ready.set()
            return {**row,'ollama_processes':[{'pid':1234567,'name':'llama-server.exe'}]}
        return row
    class Memory:
        def low(self): return False
        def close(self): pass
    def fake_request(*args,**kwargs):
        signal=kwargs['cancellation']
        assert ready.wait(2)
        signal.emit_stream_event({'type':'stream_content','done':False,'content_characters':1,'timestamp_monotonic':time.monotonic()})
        deadline=time.monotonic()+2
        while not signal.cancelled and time.monotonic()<deadline: time.sleep(.01)
        signal.emit_stream_event({'type':'request_closed','reason':'cancelled'})
        signal.throw_if_cancelled()
        raise AssertionError('cancel not sent')
    with patch.object(manual,'ROOT',tmp_path), patch.object(manual,'WindowsLowMemory',Memory), \
         patch.object(manual,'active_ollama_connections',return_value=[]), \
         patch.object(manual.telemetry,'sample',side_effect=sample), \
         patch.object(manual.telemetry,'get_json',return_value={'version':'0.40.16'}), \
         patch.object(manual,'unload_target_if_uncontended',return_value={'status':'UNLOADED'}), \
         patch.object(manual.psutil,'pid_exists',return_value=False), \
         patch.object(manual,'request_json',side_effect=fake_request):
        assert manual.calibrate(cancel_on_token=True)==0
    record=json.loads(next((tmp_path/'reports'/'qwen4b_manual_qa').glob('cancel_active_*.json')).read_text(encoding='utf-8'))
    assert record['status']=='VERIFIED' and record['observed_runner_pids']==[1234567]
    assert record['events'][0]['type']=='stream_content'


def test_unload_does_not_touch_model_when_another_client_is_active():
    from types import SimpleNamespace
    conn=SimpleNamespace(status='ESTABLISHED',pid=999999,laddr=SimpleNamespace(port=54000),raddr=SimpleNamespace(port=11434))
    with patch.object(manual.psutil,'net_connections',return_value=[conn]), patch.object(manual.subprocess,'run') as stop:
        assert manual.unload_target_if_uncontended()['status']=='BLOCKED_EXTERNAL_CLIENT'
        stop.assert_not_called()


def test_unload_reports_failure_instead_of_claiming_success():
    from types import SimpleNamespace
    with patch.object(manual.psutil,'net_connections',return_value=[]), \
         patch.object(manual.telemetry,'get_json',return_value={'models':[model()]}), \
         patch.object(manual.subprocess,'run',return_value=SimpleNamespace(returncode=1,stderr='failed')):
        assert manual.unload_target_if_uncontended()['status']=='STOP_ERROR'


def test_requested_concept_question_retrieves_oxygen_bmp_and_kinetics():
    from src.recommendations.retrieval import retrieve
    query='Объясни разницу между BMP, теоретическим максимальным выходом метана и фактическим выходом метана за 30 дней. Нужен ли кислород для метаногенеза?'
    found=retrieve(query)
    ids={claim['id'] for claim in found['claims']}
    assert {'q4b_anaerobic_no_oxygen','q4b_bmp_not_theoretical_maximum','q4b_timed_reactor_yield_kinetics'} <= ids
