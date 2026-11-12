import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
from threading import Thread
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluations import real_qwen_baseline_runner as runner


def test_utf8_case_file_roundtrips_ru_kk_en_math_units_and_ch4():
    cases = runner.load_cases()
    probes = cases['unicode_probe']
    assert all(letter in probes['kk'] for letter in 'әғқңөұүһі')
    assert 'BMP' in probes['en']
    assert '×' in probes['symbols_units']
    assert 'CH₄' in probes['symbols_units']
    assert '°C' in probes['symbols_units']
    assert 'м³' in probes['symbols_units'] and 'm³' in probes['symbols_units']
    assert len(cases['scenarios']) == 4


@pytest.mark.parametrize('text', [
    'Чем BMP отличается от выхода реактора?',
    'әғқңөұүһі',
    'Explain BMP versus actual reactor yield.',
    '0,6 кг VS × 250 мл CH₄/г VS = 0,15 м³; 35 °C; 90 L; ± ≤ ≥ →',
])
def test_text_roundtrip_is_byte_identical(text):
    original = text.encode('utf-8', errors='strict')
    encoded = runner.validate_text_roundtrip(text)
    assert encoded == original
    assert encoded.decode('utf-8').encode('utf-8') == original


@pytest.mark.parametrize('text', ['???', 'BMP\ufffd yield', '\ud800'])
def test_damaged_unicode_is_rejected_before_http(text):
    with patch.object(runner, 'http_json') as send:
        with pytest.raises(runner.InvalidInput):
            runner.validate_text_roundtrip(text)
        send.assert_not_called()


def test_corrupted_scenario_is_rejected_before_any_dashboard_http_call():
    scenario = {'id': 'bad', 'language': 'ru', 'conversation': 'bad', 'message': '??? BMP'}
    with patch.object(runner, 'http_json') as send:
        with pytest.raises(runner.InvalidInput):
            runner._run_one_case('http://127.0.0.1:9999', scenario, {}, 1,
                                 'http://127.0.0.1:11434', Path('unused.log'), 0,
                                 Path('unused.json'), {'scenarios': []})
        send.assert_not_called()


def test_json_http_body_uses_utf8_and_preserves_exact_message_bytes():
    message = 'Ғалым: BMP — лабораториялық тест; 0,6 kg VS × 250 мл CH₄/г VS = 0,15 м³.'
    body = runner.json_body({'message': message, 'request_id': 'roundtrip'})
    restored = json.loads(body.decode('utf-8', errors='strict'))
    assert restored['message'].encode('utf-8') == message.encode('utf-8')


def test_actual_loopback_http_echo_preserves_utf8_body_bytes():
    received = []

    class Echo(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers['Content-Length']))
            received.append(body)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Echo)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        message = 'Қазақша: әғқңөұүһі; метан CH₄ × 250 мл/г VS; 35 °C.'
        payload = {'message': message}
        body = runner.json_body(payload)
        request = runner.urllib.request.Request(
            f'http://127.0.0.1:{server.server_port}/echo', data=body, method='POST',
            headers={'Content-Type': 'application/json; charset=utf-8'},
        )
        with runner.urllib.request.urlopen(request, timeout=3) as response:
            echoed = response.read()
        assert echoed == body
        assert received == [body]
        assert json.loads(echoed.decode('utf-8'))['message'].encode('utf-8') == message.encode('utf-8')
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _sample(ram=10000, temperature=56):
    return {
        'memory': {'available_ram_mib': ram},
        'gpu': {'temperature_c': temperature, 'hw_thermal_slowdown': 'Not Active',
                'sw_thermal_slowdown': 'Not Active'},
        'ollama': {'ps': {'models': []}, 'models_installed': ['qwen3:8b']},
        'processes': {'ollama_server': [{'pid': 11}], 'ollama_app': [{'pid': 12}], 'llama_server': []},
        'active_ollama_connections': [],
    }


def test_admission_and_runtime_ram_gates_are_separate_and_evidence_based():
    assert runner.RAM_ADMISSION_MIB == pytest.approx(9373.6)
    assert runner.sample_gate_reasons(_sample(ram=9373.6), admission=True) == []
    assert runner.sample_gate_reasons(_sample(ram=9000), admission=True) == [
        'cold_start_ram_below_provisional_9373.6_MiB'
    ]
    assert runner.sample_gate_reasons(_sample(ram=6246.4), admission=False) == []
    assert runner.sample_gate_reasons(_sample(ram=6246.3), admission=False) == [
        'runtime_ram_below_6246.4_MiB'
    ]


def test_admission_blocks_loaded_or_busy_ollama_and_duplicate_runners():
    loaded = _sample()
    loaded['ollama']['ps']['models'] = [{'name': 'qwen3:8b'}]
    loaded['active_ollama_connections'] = [{'pid': 99}]
    loaded['processes']['llama_server'] = [{'pid': 101}, {'pid': 102}]
    reasons = runner.sample_gate_reasons(loaded, admission=True)
    assert 'ollama_model_already_loaded_before_qa' in reasons
    assert 'ollama_request_already_active_before_qa' in reasons
    assert 'llama_server_runner_already_active_before_qa' in reasons


def test_local_temperature_stop_uses_device_target_margin_and_slowdown_signal():
    unsafe = _sample(temperature=82)
    unsafe['gpu']['hw_thermal_slowdown'] = 'Active'
    reasons = runner.sample_gate_reasons(unsafe, admission=False)
    assert 'gpu_temperature_at_or_above_local_stop_82_C' in reasons
    assert 'gpu_thermal_slowdown_active' in reasons


def test_blocked_admission_never_starts_qa_backend(tmp_path):
    output = tmp_path / 'blocked.json'
    blocked = {'gate': {'status': 'BLOCKED', 'reasons': ['cold_start_ram_below_provisional_9373.6_MiB']},
               'samples': []}
    with patch.object(runner, 'three_point_preflight', return_value=blocked), \
         patch.object(runner.subprocess, 'Popen') as start_backend:
        result = runner.run_baseline(runner.DEFAULT_CASES, output, 'http://127.0.0.1:11434')
    assert result == 2
    assert not start_backend.called
    trace = json.loads(output.read_text(encoding='utf-8'))
    assert trace['status'] == 'BLOCKED_PRELOAD_ADMISSION'
    assert trace['blocked_reasons'] == blocked['gate']['reasons']


def test_ollama_effective_config_parser_only_returns_relevant_settings(tmp_path):
    log = tmp_path / 'server.log'
    log.write_text(
        'time=x level=INFO msg="server config" env="map[OLLAMA_KEEP_ALIVE:5m0s '
        'OLLAMA_NUM_PARALLEL:1 OLLAMA_CONTEXT_LENGTH:0 OLLAMA_MAX_LOADED_MODELS:0 '
        'OLLAMA_MAX_QUEUE:512 OLLAMA_LOAD_TIMEOUT:5m0s OTHER:ignored]"\n', encoding='utf-8'
    )
    config = runner.ollama_effective_config(log)
    assert config['OLLAMA_KEEP_ALIVE'] == '5m0s'
    assert config['OLLAMA_NUM_PARALLEL'] == '1'
    assert config['OLLAMA_CONTEXT_LENGTH'] == '0'
    assert 'OTHER' not in config


def test_llama_server_load_flags_are_captured_and_checked_without_running_model():
    line = ('time=2026-11-09T23:08:08Z msg="starting llama-server" '
            'cmd="C:\\Ollama\\llama-server.exe --model qwen --port 1234 -c 8192 -np 1 '
            '-b 64 -ub 64 -ngl 16 -t 6"')
    config = runner.parse_llama_launch(line)
    assert config == {'context': 8192, 'parallel': 1, 'batch': 64, 'ubatch': 64, 'gpu_layers': 16}
    assert runner.launch_config_reasons(config) == []
    assert runner.launch_config_reasons({'context': 4096})
