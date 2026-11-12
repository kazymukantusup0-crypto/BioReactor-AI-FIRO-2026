"""Bounded, UTF-8-safe real-Qwen baseline harness for Windows loopback QA.

No inference is performed by default. Use ``validate`` or ``preflight`` first;
``run --allow-real-inference`` is the only command that starts Qwen.
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = ROOT / 'evaluations' / 'real_qwen_baseline_cases_20261109.json'
RAM_RUNTIME_GATE_MIB = 6246.4
# Previous controlled run fell from 7900.2 to 4773.0 MiB during this QA load
# profile. The provisional admission floor retains the established runtime
# reserve after that observed 3127.2 MiB load-time drop.
OBSERVED_LOAD_DROP_MIB = 3127.2
RAM_ADMISSION_MIB = RAM_RUNTIME_GATE_MIB + OBSERVED_LOAD_DROP_MIB
GPU_DEVICE_TARGET_C = 87
GPU_STOP_C = GPU_DEVICE_TARGET_C - 5
OLLAMA_VERSION_REQUIRED = 'ollama version is 0.40.15'
MODEL = 'qwen3:8b'
KAZAKH_CHARS = tuple('әғқңөұүһі')
REQUIRED_CASE_IDS = {
    'bmp_vs_actual_yield', 'mixed_science_calculation', 'batch_5kg', 'correct_batch_to_6kg'
}


class InvalidInput(ValueError):
    """Prompt bytes or baseline fixture failed integrity checks."""


class TelemetryError(RuntimeError):
    """A required local resource signal could not be read reliably."""


def validate_text_roundtrip(text: str) -> bytes:
    if not isinstance(text, str):
        raise InvalidInput('text must be a Unicode string')
    if '\ufffd' in text or re.search(r'\?{2,}', text):
        raise InvalidInput('replacement characters or repeated question marks suggest damaged input')
    try:
        encoded = text.encode('utf-8', errors='strict')
        restored = encoded.decode('utf-8', errors='strict')
    except UnicodeError as exc:
        raise InvalidInput(f'text is not valid Unicode/UTF-8: {type(exc).__name__}') from None
    if restored != text or restored.encode('utf-8', errors='strict') != encoded:
        raise InvalidInput('UTF-8 round-trip changed the original text')
    return encoded


def _compare_strings(original: Any, restored: Any, where: str = '$') -> None:
    if isinstance(original, str):
        if not isinstance(restored, str) or validate_text_roundtrip(original) != validate_text_roundtrip(restored):
            raise InvalidInput(f'JSON UTF-8 round-trip changed string at {where}')
    elif isinstance(original, dict):
        if not isinstance(restored, dict) or original.keys() != restored.keys():
            raise InvalidInput(f'JSON object structure changed at {where}')
        for key in original:
            _compare_strings(key, key, where + '.<key>')
            _compare_strings(original[key], restored[key], where + '.' + str(key))
    elif isinstance(original, list):
        if not isinstance(restored, list) or len(original) != len(restored):
            raise InvalidInput(f'JSON array structure changed at {where}')
        for i, (left, right) in enumerate(zip(original, restored)):
            _compare_strings(left, right, f'{where}[{i}]')
    elif original != restored:
        raise InvalidInput(f'JSON value changed at {where}')


def json_body(payload: dict[str, Any]) -> bytes:
    """Serialize with Python, then verify the exact UTF-8 text before send."""
    try:
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8', errors='strict')
        restored = json.loads(body.decode('utf-8', errors='strict'))
    except (TypeError, ValueError, UnicodeError) as exc:
        raise InvalidInput(f'HTTP JSON is not UTF-8 round-trip safe: {type(exc).__name__}') from None
    _compare_strings(payload, restored)
    return body


def load_cases(path: Path = DEFAULT_CASES) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        text = raw.decode('utf-8', errors='strict')
        decoded = json.loads(text)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise InvalidInput(f'case file must be valid UTF-8 JSON: {type(exc).__name__}') from None
    if not isinstance(decoded, dict) or decoded.get('schema_version') != 1:
        raise InvalidInput('unsupported baseline case file schema')
    probes = decoded.get('unicode_probe')
    if not isinstance(probes, dict) or not {'ru', 'kk', 'en', 'symbols_units'} <= set(probes):
        raise InvalidInput('missing RU/KK/EN/symbols Unicode probes')
    for value in probes.values():
        validate_text_roundtrip(value)
    if not re.search(r'[А-Яа-яЁё]', probes['ru']):
        raise InvalidInput('Russian Unicode probe is missing Cyrillic')
    if not all(char in probes['kk'] for char in KAZAKH_CHARS):
        raise InvalidInput('Kazakh Unicode probe is missing one or more required letters')
    if not re.search(r'\bBMP\b', probes['en'], re.I):
        raise InvalidInput('English Unicode probe is missing BMP text')
    for symbol in ('×', 'CH₄', 'm³', '°C', '±', '≤', '≥', '→', 'VS', 'kg', 'L'):
        if symbol not in probes['symbols_units']:
            raise InvalidInput(f'symbol/unit probe is missing {symbol!r}')
    scenarios = decoded.get('scenarios')
    if not isinstance(scenarios, list) or any(not isinstance(row, dict) for row in scenarios):
        raise InvalidInput('baseline scenarios must be a list of objects')
    if {row.get('id') for row in scenarios} != REQUIRED_CASE_IDS:
        raise InvalidInput('baseline scenarios do not match the four required sequential turns')
    seen = set()
    for row in scenarios:
        if not isinstance(row, dict) or not isinstance(row.get('message'), str):
            raise InvalidInput('every baseline scenario must contain a text message')
        validate_text_roundtrip(row['message'])
        if row.get('id') in seen:
            raise InvalidInput('duplicate scenario id')
        seen.add(row['id'])
        if row.get('language') == 'ru' and not re.search(r'[А-Яа-яЁё]', row['message']):
            raise InvalidInput(f'Russian scenario {row["id"]} has no Cyrillic text')
    # Verify the case file itself round-trips in the same JSON representation
    # used by the HTTP client, before any endpoint is contacted.
    json_body(decoded)
    return decoded


def http_json(method: str, url: str, payload: dict[str, Any] | None = None, timeout: float = 5.0) -> tuple[Any, bytes]:
    body = None if payload is None else json_body(payload)
    headers = {'Accept': 'application/json'}
    if body is not None:
        headers['Content-Type'] = 'application/json; charset=utf-8'
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_body = response.read()
        decoded = json.loads(response_body.decode('utf-8', errors='strict'))
    except (urllib.error.URLError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TelemetryError(f'{method} {url} failed: {type(exc).__name__}: {exc}') from None
    return decoded, body or b''


def _run_text(args: list[str], timeout: float = 5.0) -> str:
    try:
        completed = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace',
                                   timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TelemetryError(f'command unavailable: {Path(args[0]).name}: {type(exc).__name__}') from None
    if completed.returncode != 0:
        raise TelemetryError(f'{Path(args[0]).name} returned {completed.returncode}: {completed.stderr[-400:]}')
    return completed.stdout.strip()


class _PerformanceInformation(ctypes.Structure):
    _fields_ = [
        ('cb', ctypes.wintypes.DWORD), ('CommitTotal', ctypes.c_size_t),
        ('CommitLimit', ctypes.c_size_t), ('CommitPeak', ctypes.c_size_t),
        ('PhysicalTotal', ctypes.c_size_t), ('PhysicalAvailable', ctypes.c_size_t),
        ('SystemCache', ctypes.c_size_t), ('KernelTotal', ctypes.c_size_t),
        ('KernelPaged', ctypes.c_size_t), ('KernelNonpaged', ctypes.c_size_t),
        ('PageSize', ctypes.c_size_t), ('HandleCount', ctypes.wintypes.DWORD),
        ('ProcessCount', ctypes.wintypes.DWORD), ('ThreadCount', ctypes.wintypes.DWORD),
    ]


def memory_sample() -> dict[str, float]:
    if os.name != 'nt':
        raise TelemetryError('GetPerformanceInfo memory telemetry requires Windows')
    try:
        psapi = ctypes.WinDLL('Psapi.dll')
        fn = psapi.GetPerformanceInfo
        fn.argtypes = [ctypes.POINTER(_PerformanceInformation), ctypes.wintypes.DWORD]
        fn.restype = ctypes.wintypes.BOOL
        info = _PerformanceInformation()
        info.cb = ctypes.sizeof(info)
        if not fn(ctypes.byref(info), info.cb) or info.PageSize <= 0:
            raise OSError('GetPerformanceInfo returned false')
    except (OSError, AttributeError) as exc:
        raise TelemetryError(f'Windows memory telemetry unavailable: {type(exc).__name__}: {exc}') from None
    mib = 1024 * 1024
    return {
        'available_ram_mib': round(info.PhysicalAvailable * info.PageSize / mib, 1),
        'commit_headroom_mib': round((info.CommitLimit - info.CommitTotal) * info.PageSize / mib, 1),
        'commit_total_mib': round(info.CommitTotal * info.PageSize / mib, 1),
        'commit_limit_mib': round(info.CommitLimit * info.PageSize / mib, 1),
    }


def _gpu_sample() -> dict[str, Any]:
    executable = shutil.which('nvidia-smi')
    if not executable:
        raise TelemetryError('nvidia-smi telemetry is unavailable')
    row = _run_text([executable, '--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw,pstate',
                     '--format=csv,noheader,nounits']).split(',')
    if len(row) != 7:
        raise TelemetryError('unexpected nvidia-smi query result')
    detail = _run_text([executable, '-q', '-d', 'PERFORMANCE,TEMPERATURE'])
    hw = re.search(r'HW Thermal Slowdown\s*:\s*(Active|Not Active)', detail)
    sw = re.search(r'SW Thermal Slowdown\s*:\s*(Active|Not Active)', detail)
    if not hw or not sw:
        raise TelemetryError('thermal slowdown telemetry is unavailable')
    def as_int(value: str) -> int:
        return int(value.strip())
    try:
        return {
            'name': row[0].strip(), 'temperature_c': as_int(row[1]), 'utilization_pct': as_int(row[2]),
            'vram_used_mib': as_int(row[3]), 'vram_total_mib': as_int(row[4]),
            'power_w': float(row[5].strip()), 'pstate_diagnostic_only': row[6].strip(),
            'hw_thermal_slowdown': hw.group(1), 'sw_thermal_slowdown': sw.group(1),
            'device_target_c_from_prior_local_telemetry': GPU_DEVICE_TARGET_C,
            'configured_local_stop_c': GPU_STOP_C,
        }
    except (ValueError, IndexError):
        raise TelemetryError('nvidia-smi returned incomplete numeric telemetry') from None


def _endpoint_port(value: str) -> int | None:
    match = re.search(r':(\d+)$', value)
    return int(match.group(1)) if match else None


def _connection_sample() -> list[dict[str, Any]]:
    output = _run_text(['netstat', '-ano', '-p', 'tcp'])
    rows = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[0].upper() != 'TCP':
            continue
        local_port = _endpoint_port(parts[1])
        remote_port = _endpoint_port(parts[2])
        if local_port != 11434 and remote_port != 11434:
            continue
        try:
            pid = int(parts[4])
        except ValueError:
            continue
        rows.append({'local': parts[1], 'remote': parts[2], 'state': parts[3], 'pid': pid,
                     'client_request_candidate': remote_port == 11434 and parts[3].upper() == 'ESTABLISHED'})
    return rows


def _process_sample() -> dict[str, list[dict[str, Any]]]:
    powershell = shutil.which('powershell.exe') or r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
    command = ("Get-Process -ErrorAction Stop | Where-Object { $_.ProcessName -match '^(ollama|llama-server)' } "
               "| Select-Object ProcessName,Id,WorkingSet64 | ConvertTo-Json -Compress")
    output = _run_text([powershell, '-NoProfile', '-NonInteractive', '-Command', command])
    try:
        rows = json.loads(output) if output else []
    except json.JSONDecodeError:
        raise TelemetryError('PowerShell process telemetry returned invalid JSON') from None
    if isinstance(rows, dict):
        rows = [rows]
    result: dict[str, list[dict[str, Any]]] = {'ollama_server': [], 'ollama_app': [], 'llama_server': []}
    for row in rows:
        name = str(row.get('ProcessName', '')).casefold()
        group = 'ollama_app' if name.startswith('ollama app') else 'ollama_server' if name == 'ollama' else 'llama_server'
        try:
            pid = int(row['Id'])
            working_set = int(row['WorkingSet64'])
        except (KeyError, TypeError, ValueError):
            raise TelemetryError('PowerShell process telemetry omitted PID or working set') from None
        result[group].append({'name': row['ProcessName'], 'pid': pid,
                              'working_set_bytes': working_set,
                              'working_set_mib': round(working_set / (1024 * 1024), 1)})
    return result


def _ollama_info(base_url: str) -> dict[str, Any]:
    ps, _ = http_json('GET', base_url.rstrip('/') + '/api/ps')
    tags, _ = http_json('GET', base_url.rstrip('/') + '/api/tags')
    return {'ps': ps, 'models_installed': [x.get('name') for x in tags.get('models', [])]}


def collect_sample(phase: str, ollama_url: str, qa_pid: int | None = None) -> dict[str, Any]:
    try:
        sample = {
            'timestamp_local': datetime.now().astimezone().isoformat(), 'phase': phase,
            'memory': memory_sample(), 'gpu': _gpu_sample(), 'processes': _process_sample(),
            'ollama_connections': _connection_sample(), 'qa_backend_pid': qa_pid,
            'ollama': _ollama_info(ollama_url),
        }
    except TelemetryError:
        raise
    sample['active_ollama_connections'] = [row for row in sample['ollama_connections']
                                            if row['client_request_candidate']]
    sample['active_qa_ollama_connections'] = [row for row in sample['active_ollama_connections']
                                               if row['pid'] == qa_pid]
    sample['active_external_ollama_connections'] = [row for row in sample['active_ollama_connections']
                                                     if qa_pid is None or row['pid'] != qa_pid]
    return sample


def sample_gate_reasons(sample: dict[str, Any], *, admission: bool) -> list[str]:
    reasons = []
    ram = sample['memory']['available_ram_mib']
    if admission and ram < RAM_ADMISSION_MIB:
        reasons.append(f'cold_start_ram_below_provisional_{RAM_ADMISSION_MIB:.1f}_MiB')
    if not admission and ram < RAM_RUNTIME_GATE_MIB:
        reasons.append(f'runtime_ram_below_{RAM_RUNTIME_GATE_MIB:.1f}_MiB')
    gpu = sample['gpu']
    if gpu['temperature_c'] >= GPU_STOP_C:
        reasons.append(f'gpu_temperature_at_or_above_local_stop_{GPU_STOP_C}_C')
    if gpu['hw_thermal_slowdown'] != 'Not Active' or gpu['sw_thermal_slowdown'] != 'Not Active':
        reasons.append('gpu_thermal_slowdown_active')
    if admission and sample['ollama'].get('ps', {}).get('models'):
        reasons.append('ollama_model_already_loaded_before_qa')
    if not admission:
        loaded = sample['ollama'].get('ps', {}).get('models', [])
        unexpected = [model.get('name') for model in loaded
                      if str(model.get('name', '')).split(':')[0] != MODEL.split(':')[0]]
        if unexpected:
            reasons.append('unexpected_ollama_model_loaded_during_qa:' + ','.join(map(str, unexpected)))
    if admission and sample['active_ollama_connections']:
        reasons.append('ollama_request_already_active_before_qa')
    if admission and sample['processes'].get('llama_server'):
        reasons.append('llama_server_runner_already_active_before_qa')
    if len(sample['processes'].get('ollama_server', [])) != 1:
        reasons.append('ollama_server_process_count_not_one')
    if MODEL not in sample['ollama'].get('models_installed', []):
        reasons.append(f'{MODEL}_not_installed')
    return reasons


def ollama_effective_config(log_path: Path | None = None) -> dict[str, Any]:
    if log_path is None:
        local = os.environ.get('LOCALAPPDATA')
        log_path = Path(local) / 'Ollama' / 'server.log' if local else Path()
    if not log_path.is_file():
        return {'status': 'log_unavailable'}
    text = log_path.read_text(encoding='utf-8', errors='replace')
    matches = re.findall(r'msg="server config".*?env="map\[(.*?)\]"', text)
    if not matches:
        return {'status': 'config_line_not_found'}
    env = matches[-1]
    keys = ('OLLAMA_KEEP_ALIVE', 'OLLAMA_NUM_PARALLEL', 'OLLAMA_CONTEXT_LENGTH',
            'OLLAMA_MAX_LOADED_MODELS', 'OLLAMA_MAX_QUEUE', 'OLLAMA_LOAD_TIMEOUT')
    result = {key: (m.group(1) if (m := re.search(rf'{key}:([^\s\]]+)', env)) else 'not_logged')
              for key in keys}
    result['source'] = str(log_path)
    return result


def three_point_preflight(ollama_url: str, interval_seconds: float = 10.0) -> dict[str, Any]:
    if interval_seconds < 10:
        raise ValueError('preflight interval must be at least 10 seconds')
    started = datetime.now().astimezone().isoformat()
    version = _run_text([shutil.which('ollama') or 'ollama', '--version'])
    config = ollama_effective_config()
    points = []
    next_at = time.monotonic()
    for index in range(3):
        if index:
            next_at += interval_seconds
            time.sleep(max(0.0, next_at - time.monotonic()))
        points.append(collect_sample(f'preflight_{index + 1}', ollama_url))
    reasons = sorted({reason for point in points for reason in sample_gate_reasons(point, admission=True)})
    if version != OLLAMA_VERSION_REQUIRED:
        reasons.append(f'ollama_version_mismatch:{version}')
    if config.get('OLLAMA_NUM_PARALLEL') != '1':
        reasons.append('ollama_num_parallel_not_confirmed_as_one')
    return {
        'started_at': started, 'finished_at': datetime.now().astimezone().isoformat(),
        'ollama_version': version, 'effective_ollama_config': config,
        'gate': {
            'status': 'PASS' if not reasons else 'BLOCKED', 'admission_ram_mib': RAM_ADMISSION_MIB,
            'runtime_ram_mib': RAM_RUNTIME_GATE_MIB, 'admission_basis':
            'one failed cold-load observation: 7900.2 -> 4773.0 MiB (3127.2 MiB drop), added to the established 6246.4 MiB runtime floor; provisional for qwen3:8b, context8192, GPU layers16, batch64',
            'temperature_stop_c': GPU_STOP_C, 'device_target_c': GPU_DEVICE_TARGET_C,
            'thermal_slowdown_required_inactive': True, 'reasons': reasons,
        },
        'samples': points,
    }


def read_log_delta(path: Path, offset: int) -> tuple[int, list[str]]:
    if not path.is_file():
        return offset, []
    with path.open('rb') as stream:
        size = stream.seek(0, os.SEEK_END)
        if size < offset:
            offset = 0
        stream.seek(offset)
        data = stream.read()
    return size, data.decode('utf-8', errors='replace').splitlines()


def parse_llama_launch(line: str) -> dict[str, int] | None:
    if 'starting llama-server' not in line.casefold():
        return None
    fields = {'context': r'\s-c\s+(\d+)', 'parallel': r'\s-np\s+(\d+)',
              'batch': r'\s-b\s+(\d+)', 'ubatch': r'\s-ub\s+(\d+)',
              'gpu_layers': r'\s-ngl\s+(\d+)'}
    result = {}
    for key, pattern in fields.items():
        match = re.search(pattern, line)
        if not match:
            return None
        result[key] = int(match.group(1))
    return result


def launch_config_reasons(config: dict[str, int] | None) -> list[str]:
    expected = {'context': 8192, 'parallel': 1, 'batch': 64, 'ubatch': 64, 'gpu_layers': 16}
    if config is None:
        return ['ollama_llama_server_launch_config_unobserved']
    return [f'ollama_launch_{key}_expected_{value}_got_{config.get(key)}'
            for key, value in expected.items() if config.get(key) != value]


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return int(sock.getsockname()[1])


def _terminal(job: dict[str, Any]) -> bool:
    return bool(job.get('terminal')) or job.get('status') in {'COMPLETED', 'FAILED', 'CANCELLED', 'TIMED_OUT'}


def _cancel_job(base_url: str, identifier: str) -> dict[str, Any] | None:
    try:
        result, _ = http_json('POST', f'{base_url}/api/dashboard/jobs/{identifier}/cancel', {}, timeout=3)
        return result
    except TelemetryError:
        return None


def _wait_cancel(base_url: str, identifier: str, seconds: float = 20.0) -> dict[str, Any] | None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            job, _ = http_json('GET', f'{base_url}/api/dashboard/jobs/{identifier}', timeout=3)
        except TelemetryError:
            return None
        if _terminal(job):
            return job
        time.sleep(0.25)
    return None


def _model_ready(sample: dict[str, Any]) -> bool:
    return any(str(model.get('name', '')).split(':')[0] == MODEL.split(':')[0]
               for model in sample['ollama'].get('ps', {}).get('models', []))


def _generation_confirmed(reply: dict[str, Any]) -> bool:
    for provider in reply.get('provider_status', []):
        if provider.get('model') == MODEL and provider.get('actual_generation') is True:
            return True
        for request in provider.get('requests', []):
            if request.get('actual_generation') is True and provider.get('model') == MODEL:
                return True
    return False


def _score(scenario_id: str, reply: dict[str, Any], snapshot: dict[str, Any] | None) -> dict[str, Any]:
    answer = str(reply.get('answer', ''))
    low = answer.casefold()
    tools = [row.get('tool') for row in reply.get('tools', []) if isinstance(row, dict)]
    checks: dict[str, Any] = {'real_qwen_generation': _generation_confirmed(reply)}
    if scenario_id == 'bmp_vs_actual_yield':
        checks.update({
            'source_search_called': 'search_scientific_sources' in tools,
            'batch_assessment_not_called': 'assess_substrate_potential' not in tools,
            'concept_explained': bool(re.search(r'лаборатор|batch', low) and re.search(r'потенциал|измер|фактическ|actual', low)),
            'did_not_request_batch_parameters': not bool(re.search(r'уточн\w*.{0,80}(?:массу|сырь|субстрат)|укажите.{0,80}(?:кг|массу)', low)),
            'no_numeric_yield_claim': not bool(re.search(r'\b\d+[.,]?\d*\s*(?:мл\s*(?:ch₄|метан)|м³|m3)\b', low)),
        })
    elif scenario_id == 'mixed_science_calculation':
        checks.update({
            'source_search_called': 'search_scientific_sources' in tools,
            'batch_assessment_not_called': 'assess_substrate_potential' not in tools,
            '0_15_m3_present': bool(re.search(r'0[.,]15\s*(?:м³|m³|m3|куб)', low)),
            'scientific_explanation_present': bool(re.search(r'bmp|лаборатор|batch', low)),
        })
    elif scenario_id == 'batch_5kg':
        checks['batch_assessment_called'] = 'assess_substrate_potential' in tools
    elif scenario_id == 'correct_batch_to_6kg':
        facts = (snapshot or {}).get('memory', {}).get('facts', {})
        quantity = facts.get('quantity') or facts.get('mass_kg') or {}
        material = facts.get('material') or {}
        capacity = facts.get('reactor_total_volume_l') or {}
        checks.update({
            'batch_assessment_called': 'assess_substrate_potential' in tools,
            'quantity_is_6_kg': quantity.get('value') in (6, 6.0),
            'material_preserved': material.get('value') == 'food_waste',
            'reactor_capacity_is_90_l': capacity.get('value') in (90, 90.0),
            'answer_not_scored_as_measurement': bool(re.search(r'расч[её]т|potential|оценк|предвар', low)),
        })
    return checks


def _write_trace(path: Path, trace: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(trace, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8', errors='strict')
    restored = json.loads(body.decode('utf-8', errors='strict'))
    _compare_strings(trace, restored)
    temp_path = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temp_path.write_bytes(body)
    os.replace(temp_path, path)


def _server_log_path() -> Path:
    local = os.environ.get('LOCALAPPDATA')
    if not local:
        raise TelemetryError('LOCALAPPDATA is unavailable; cannot monitor Ollama server log')
    path = Path(local) / 'Ollama' / 'server.log'
    if not path.is_file():
        raise TelemetryError(f'Ollama log is unavailable: {path}')
    return path


def _case_session(base_url: str, key: str, sessions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if key in sessions:
        current, _ = http_json('GET', f'{base_url}/api/dashboard/chat/sessions/{sessions[key]["id"]}')
        return current
    created, _ = http_json('POST', f'{base_url}/api/dashboard/chat/sessions',
                           {'mode': 'offline', 'context': {}, 'conversation_version': '7'})
    sessions[key] = {'id': created['id'], 'state_version': created.get('state_version', 0)}
    return created


def _run_one_case(base_url: str, scenario: dict[str, Any], sessions: dict[str, dict[str, Any]],
                  qa_pid: int, ollama_url: str, log_path: Path, log_offset: int,
                  trace_path: Path, trace: dict[str, Any]) -> tuple[dict[str, Any], int, bool]:
    prompt = scenario['message']
    prompt_bytes = validate_text_roundtrip(prompt)
    session_key = scenario['conversation']
    session = _case_session(base_url, session_key, sessions)
    sid = sessions[session_key]['id']
    expected = session.get('state_version', sessions[session_key].get('state_version', 0))
    request_id = 'QWEN_UTF8_' + scenario['id'].upper() + '_' + uuid.uuid4().hex[:8]
    payload = {'message': prompt, 'request_id': request_id, 'expected_state_version': expected}
    payload_bytes = json_body(payload)
    if json.loads(payload_bytes.decode('utf-8'))['message'].encode('utf-8') != prompt_bytes:
        raise InvalidInput('request message changed before HTTP transmission')
    record: dict[str, Any] = {
        'id': scenario['id'], 'language': scenario['language'], 'prompt': prompt,
        'prompt_sha256': __import__('hashlib').sha256(prompt_bytes).hexdigest(),
        'request_json_sha256': __import__('hashlib').sha256(payload_bytes).hexdigest(),
        'session_id': sid, 'expected_state_version': expected, 'request_id': request_id,
        'status': 'SUBMITTING', 'phases': [], 'telemetry': [],
    }
    before = collect_sample('before_load', ollama_url, qa_pid)
    reasons = sample_gate_reasons(before, admission=False)
    if reasons:
        record.update(status='BLOCKED', block_reasons=reasons, before_load=before)
        trace['scenarios'].append(record);_write_trace(trace_path, trace)
        return record, log_offset, True
    record['before_load'] = before
    accepted, sent = http_json('POST', f'{base_url}/api/dashboard/chat/sessions/{sid}/jobs', payload, timeout=10)
    if sent != payload_bytes:
        raise InvalidInput('serialized request bytes differ between preflight and HTTP client')
    record['accepted_job'] = accepted
    if accepted.get('message') != prompt or not isinstance(accepted.get('message'), str) or accepted['message'].encode('utf-8') != prompt_bytes:
        cancel = _cancel_job(base_url, accepted.get('id', '')) if accepted.get('id') else None
        terminal = _wait_cancel(base_url, accepted['id']) if accepted.get('id') else None
        record.update(status='INVALID_INPUT', backend_echo_mismatch=True, cancel=cancel, terminal_job=terminal)
        trace['scenarios'].append(record);_write_trace(trace_path, trace)
        return record, log_offset, True
    record['input_integrity'] = {'status': 'PASS', 'original_utf8_sha256': record['prompt_sha256'],
                                 'backend_echo_byte_equal': True}
    job_id = accepted['id']
    record['status'] = 'RUNNING'
    start = time.monotonic()
    deadline = start + 180
    model_ready_seen = False
    inference_signal_seen = False
    generated_tokens_seen = 0
    stop = False
    stop_after_completion = False
    last_sample = 0.0
    while time.monotonic() < deadline:
        job, _ = http_json('GET', f'{base_url}/api/dashboard/jobs/{job_id}', timeout=5)
        now = time.monotonic()
        if now - last_sample >= 1.0:
            sample = collect_sample('job_running', ollama_url, qa_pid)
            log_offset, events = read_log_delta(log_path, log_offset)
            event_text = '\n'.join(events)
            launch_line = next((line for line in events if 'starting llama-server' in line.casefold()), None)
            if launch_line:
                launch_config = parse_llama_launch(launch_line)
                record['ollama_launch_config'] = launch_config
            else:
                launch_config = record.get('ollama_launch_config')
            if 'model loaded' in event_text.casefold():
                model_ready_seen = True
            ready = _model_ready(sample) or model_ready_seen
            active_task = 'processing task' in event_text.casefold()
            if ready and (sample['active_qa_ollama_connections'] or active_task):
                phase = 'during_inference'
                inference_signal_seen = True
            elif not ready and ('starting llama-server' in event_text.casefold() or sample['processes']['llama_server']):
                phase = 'during_load'
            elif ready:
                phase = 'model_ready'
            else:
                phase = 'job_active_stage_unknown'
            sample['phase'] = phase
            sample['job'] = {'status': job.get('status'), 'current_stage': job.get('current_stage'),
                             'terminal': _terminal(job)}
            sample['ollama_log_events'] = events
            sample['model_ready_observed'] = ready
            sample['inference_activity_signal'] = bool(sample['active_qa_ollama_connections'] or active_task)
            sample['external_ollama_connections'] = sample['active_external_ollama_connections']
            record['telemetry'].append(sample)
            reasons = sample_gate_reasons(sample, admission=False)
            if len(sample['processes']['llama_server']) > 1:
                reasons.append('duplicate_llama_server_runner_processes')
            if sample['active_external_ollama_connections']:
                reasons.append('external_ollama_request_detected_during_qa')
            if re.search(r'CUDA error|0xc0000409', event_text, re.I):
                reasons.append('cuda_or_runner_crash_signature')
            if launch_line:
                reasons.extend(launch_config_reasons(launch_config))
            if len(sample['active_qa_ollama_connections']) > 1:
                reasons.append('multiple_ollama_http_requests_from_qa_backend')
            if _terminal(job):
                record['terminal_job'] = job
                record['elapsed_seconds'] = round(time.monotonic() - start, 3)
                if reasons:
                    record['post_completion_block_reasons'] = reasons
                    stop_after_completion = True
                break
            if reasons:
                record['block_reasons'] = reasons
                record['cancel_request'] = _cancel_job(base_url, job_id)
                record['terminal_job_after_cancel'] = _wait_cancel(base_url, job_id)
                record['status'] = 'BLOCKED'
                stop = True
                break
            last_sample = now
            time.sleep(0.25)
        else:
            time.sleep(0.2)
    else:
        record['block_reasons'] = ['job_timeout_180s']
        record['cancel_request'] = _cancel_job(base_url, job_id)
        record['terminal_job_after_cancel'] = _wait_cancel(base_url, job_id)
        record['status'] = 'BLOCKED'
        stop = True
    if stop:
        record['after_cancel'] = collect_sample('after_cancel', ollama_url, qa_pid)
        trace['scenarios'].append(record);_write_trace(trace_path, trace)
        return record, log_offset, True
    final_job = record.get('terminal_job')
    if not final_job or final_job.get('status') != 'COMPLETED':
        record['status'] = 'FAILED'
        record['block_reasons'] = ['dashboard_job_not_completed']
        trace['scenarios'].append(record);_write_trace(trace_path, trace)
        return record, log_offset, True
    result, _ = http_json('GET', f'{base_url}{final_job["result_reference"]}', timeout=8)
    reply = result.get('reply', {})
    snapshot, _ = http_json('GET', f'{base_url}/api/dashboard/chat/sessions/{sid}', timeout=5)
    events, _ = http_json('GET', f'{base_url}/api/dashboard/jobs/{job_id}/events', timeout=5)
    after = collect_sample('after_completion', ollama_url, qa_pid)
    log_offset, final_logs = read_log_delta(log_path, log_offset)
    generated_tokens_seen = sum(int(x) for x in re.findall(r'n_gen\s*=\s*(\d+)', '\n'.join(final_logs)))
    model_ready_seen = model_ready_seen or _model_ready(after) or any('model loaded' in x.casefold() for x in final_logs)
    inference_signal_seen = inference_signal_seen or any(x.get('inference_activity_signal') for x in record['telemetry'])
    record.update({
        'status': 'COMPLETED', 'elapsed_seconds': round(time.monotonic() - start, 3),
        'raw_result': result, 'reply': reply, 'session_snapshot': snapshot, 'job_events': events,
        'after_completion': after, 'final_ollama_log_events': final_logs,
        'model_ready_observed': model_ready_seen, 'inference_activity_signal_observed': inference_signal_seen,
        'n_gen_tokens_observed_in_ollama_log': generated_tokens_seen,
        'independent_checks': _score(scenario['id'], reply, snapshot),
    })
    if scenario['id'] == 'batch_5kg':
        facts = snapshot.get('memory', {}).get('facts', {})
        quantity = facts.get('quantity') or facts.get('mass_kg') or {}
        record['independent_checks']['quantity_saved_as_5kg'] = quantity.get('value') in (5, 5.0)
        sessions[session_key]['state_version'] = snapshot.get('state_version', expected + 1)
    if scenario['id'] == 'correct_batch_to_6kg':
        sessions[session_key]['state_version'] = snapshot.get('state_version', expected + 1)
    runtime_reasons = sample_gate_reasons(after, admission=False)
    if runtime_reasons or stop_after_completion:
        record.setdefault('post_completion_block_reasons', runtime_reasons)
        record['status'] = 'COMPLETED_RESOURCE_STOP'
        stop = True
    trace['scenarios'].append(record);_write_trace(trace_path, trace)
    return record, log_offset, stop


def _unload_model(ollama_url: str, qa_pid: int, trace: dict[str, Any], trace_path: Path) -> None:
    before, _ = http_json('GET', ollama_url.rstrip('/') + '/api/ps')
    if not before.get('models'):
        trace['after_unload'] = {'status': 'ALREADY_UNLOADED', 'sample': collect_sample('after_unload', ollama_url, qa_pid)}
        _write_trace(trace_path, trace)
        return
    sample = collect_sample('before_unload', ollama_url, qa_pid)
    external = sample['active_external_ollama_connections']
    if external:
        trace['after_unload'] = {'status': 'SKIPPED_EXTERNAL_ACTIVITY', 'external_connections': external, 'sample': sample}
        _write_trace(trace_path, trace)
        return
    response, _ = http_json('POST', ollama_url.rstrip('/') + '/api/generate',
                            {'model': MODEL, 'prompt': '', 'keep_alive': 0, 'stream': False}, timeout=30)
    deadline = time.monotonic() + 20
    after = None
    while time.monotonic() < deadline:
        after, _ = http_json('GET', ollama_url.rstrip('/') + '/api/ps')
        if not after.get('models'):
            break
        time.sleep(0.5)
    sample = collect_sample('after_unload', ollama_url, qa_pid)
    trace['after_unload'] = {'status': 'VERIFIED' if not (after or {}).get('models') else 'NOT_CONFIRMED',
                             'request': {'keep_alive': 0, 'response': response}, 'api_ps': after, 'sample': sample}
    _write_trace(trace_path, trace)


def _stop_owned_process(process: subprocess.Popen[Any] | None) -> dict[str, Any]:
    if process is None:
        return {'status': 'NOT_STARTED'}
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    return {'pid': process.pid, 'return_code': process.returncode, 'status': 'STOPPED_OWN_QA_BACKEND'}


def run_baseline(case_path: Path, output_path: Path, ollama_url: str) -> int:
    cases = load_cases(case_path)
    if output_path.exists():
        raise FileExistsError(f'refusing to overwrite trace: {output_path}')
    lock_path = Path(tempfile.gettempdir()) / 'bioreactor_real_qwen_baseline.lock'
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise RuntimeError(f'another real-Qwen baseline lock exists: {lock_path}') from None
    os.close(lock_fd)
    trace: dict[str, Any] = {
        'started_at': datetime.now().astimezone().isoformat(), 'status': 'RUNNING',
        'case_file': str(case_path.resolve()), 'output': str(output_path.resolve()),
        'model': MODEL, 'ollama_url': ollama_url, 'scenario_order': [x['id'] for x in cases['scenarios']],
        'configuration': {'model_context': 8192, 'gpu_layers': 16, 'offline_research': True,
                          'parallel_requests': 1, 'keep_alive_default': '5m; not changed; unload per request after test'},
        'gate_policy': {'admission_ram_mib': RAM_ADMISSION_MIB, 'runtime_ram_mib': RAM_RUNTIME_GATE_MIB,
                        'device_target_c': GPU_DEVICE_TARGET_C, 'temperature_stop_c': GPU_STOP_C,
                        'provisional_admission_basis': 'Observed failed-load free-RAM drop in this config plus established runtime floor.'},
        'unicode_validation': {'status': 'PASS', 'probes': cases['unicode_probe'],
                               'case_count': len(cases['scenarios'])},
        'scenarios': [],
    }
    qa_process = None
    log_stream = None
    sessions: dict[str, dict[str, Any]] = {}
    own_model_may_be_loaded = False
    unload_attempted = False
    try:
        preflight = three_point_preflight(ollama_url)
        trace['preflight'] = preflight
        _write_trace(output_path, trace)
        if preflight['gate']['status'] != 'PASS':
            trace['status'] = 'BLOCKED_PRELOAD_ADMISSION'
            trace['blocked_reasons'] = preflight['gate']['reasons']
            return_code = 2
            return return_code
        qa_port = _port()
        qa_base = f'http://127.0.0.1:{qa_port}'
        qa_db = Path(tempfile.gettempdir()) / f'bioreactor_qwenqa_{datetime.now():%Y%m%d_%H%M%S}_{os.getpid()}.sqlite3'
        log_path = output_path.with_suffix('.backend.log')
        log_stream = log_path.open('ab')
        env = os.environ.copy()
        env.update({'BIOREACTOR_QA_DB': str(qa_db), 'BIOREACTOR_QA_PORT': str(qa_port), 'PYTHONUTF8': '1'})
        server_script = ROOT / 'evaluations' / 'reliability_qwen_server.py'
        qa_process = subprocess.Popen([sys.executable, '-X', 'utf8', str(server_script)], cwd=ROOT, env=env,
                                      stdout=log_stream, stderr=subprocess.STDOUT)
        trace['backend'] = {'pid': qa_process.pid, 'url': qa_base, 'isolated_db': str(qa_db),
                            'log': str(log_path), 'script': str(server_script), 'owned_process': True}
        _write_trace(output_path, trace)
        health = None
        ready_deadline = time.monotonic() + 20
        while time.monotonic() < ready_deadline and qa_process.poll() is None:
            try:
                health, _ = http_json('GET', qa_base + '/health', timeout=2)
                break
            except TelemetryError:
                time.sleep(0.25)
        if not health or health.get('scheduler_enabled') is not False or health.get('database') != str(qa_db):
            trace['status'] = 'BLOCKED_QA_BACKEND_START'
            trace['backend_start_health'] = health
            return 2
        trace['backend']['health'] = health
        log_path_ollama = _server_log_path()
        log_offset = log_path_ollama.stat().st_size
        for scenario in cases['scenarios']:
            record, log_offset, stop = _run_one_case(qa_base, scenario, sessions, qa_process.pid,
                                                      ollama_url, log_path_ollama, log_offset,
                                                      output_path, trace)
            own_model_may_be_loaded = own_model_may_be_loaded or record.get('model_ready_observed', False)
            if record.get('status') == 'BLOCKED' and record.get('cancel_request'):
                terminal = record.get('terminal_job_after_cancel') or {}
                own_model_may_be_loaded = own_model_may_be_loaded or terminal.get('status') in {'COMPLETED', 'CANCELLED'}
            if stop:
                trace['status'] = record['status']
                break
        else:
            trace['status'] = 'COMPLETED_ALL_SCENARIOS'
        unload_attempted = True
        try:
            _unload_model(ollama_url, qa_process.pid, trace, output_path)
        except TelemetryError as exc:
            trace['unload'] = {'status': 'NOT_CONFIRMED', 'error': str(exc)}
        return 0 if trace['status'] == 'COMPLETED_ALL_SCENARIOS' else 2
    except InvalidInput as exc:
        trace['status'] = 'INVALID_INPUT'
        trace['invalid_input'] = str(exc)
        return 3
    except (TelemetryError, OSError, RuntimeError, ValueError) as exc:
        trace['status'] = 'BLOCKED_INFRASTRUCTURE'
        trace['infrastructure_error'] = f'{type(exc).__name__}: {exc}'
        return 2
    finally:
        if qa_process is not None:
            if own_model_may_be_loaded and not unload_attempted:
                unload_attempted = True
                try:
                    _unload_model(ollama_url, qa_process.pid, trace, output_path)
                except Exception as exc:
                    trace.setdefault('unload', {'status': 'NOT_CONFIRMED', 'error': type(exc).__name__})
            trace['qa_backend_shutdown'] = _stop_owned_process(qa_process)
        if log_stream is not None:
            log_stream.close()
        trace['finished_at'] = datetime.now().astimezone().isoformat()
        try:
            _write_trace(output_path, trace)
        finally:
            try:
                lock_path.unlink()
            except OSError:
                pass


def _default_output() -> Path:
    return ROOT / 'reports' / f'real_qwen_baseline_{datetime.now():%Y%m%d_%H%M%S}.json'


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='strict')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('validate', 'preflight', 'run'):
        child = sub.add_parser(name)
        child.add_argument('--cases', type=Path, default=DEFAULT_CASES)
        child.add_argument('--output', type=Path)
        child.add_argument('--ollama-url', default='http://127.0.0.1:11434')
    sub.choices['run'].add_argument('--allow-real-inference', action='store_true', required=True,
                                    help='explicitly authorize model inference after all gates pass')
    args = parser.parse_args(argv)
    try:
        cases = load_cases(args.cases)
        if args.command == 'validate':
            summary = {'status': 'PASS', 'case_file': str(args.cases.resolve()),
                       'case_count': len(cases['scenarios']),
                       'unicode_probe_bytes': {key: len(value.encode('utf-8')) for key, value in cases['unicode_probe'].items()},
                       'scenario_ids': [x['id'] for x in cases['scenarios']],
                       'http_inference': 'NOT RUN'}
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0
        if args.command == 'preflight':
            result = three_point_preflight(args.ollama_url)
            result['unicode_validation'] = 'PASS'
            result['inference'] = 'NOT RUN'
            output = args.output or _default_output().with_name('qwen_preflight_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '.json')
            _write_trace(output, result)
            print(json.dumps({'status': result['gate']['status'], 'output': str(output.resolve()),
                              'reasons': result['gate']['reasons'], 'samples': result['samples']}, ensure_ascii=False, indent=2))
            return 0 if result['gate']['status'] == 'PASS' else 2
        output = args.output or _default_output()
        return run_baseline(args.cases, output, args.ollama_url)
    except InvalidInput as exc:
        print(json.dumps({'status': 'INVALID_INPUT', 'reason': str(exc)}, ensure_ascii=False))
        return 3
    except (TelemetryError, OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({'status': 'BLOCKED', 'reason': f'{type(exc).__name__}: {exc}'}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
