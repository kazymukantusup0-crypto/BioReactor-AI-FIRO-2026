"""Fail-closed, model-specific experimental admission; no model calls."""
import json
import math
from pathlib import Path

POLICY_PATH = Path(__file__).with_suffix('.json')
FIELDS = ('admission_free_ram_mib', 'runtime_free_ram_floor_mib',
          'minimum_commit_headroom_mib', 'minimum_free_vram_mib',
          'measured_peak_ram_increase_mib', 'measured_peak_commit_increase_mib',
          'measured_peak_vram_increase_mib', 'measured_abort_latency_seconds')


def load_policy():
    return json.loads(POLICY_PATH.read_text(encoding='utf-8'))


def reasons(sample, policy, *, admission):
    errors = []
    def number(value):
        return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and value >= 0
    if policy.get('model') != 'qwen3:4b-q4_K_M':
        errors.append('wrong_model_policy')
    for key in FIELDS:
        value = policy.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            errors.append('unestablished_' + key)
    if not isinstance(policy.get('justification'), str) or not policy['justification'].strip():
        errors.append('missing_profile_specific_evidence')
    if policy.get('status') != 'APPROVED_FOR_EXPERIMENT':
        errors.append('policy_not_admitted')
    if policy.get('request') != {'num_ctx':4096, 'num_batch':32, 'num_gpu':-1, 'parallel':1, 'keep_alive':0}:
        errors.append('profile_configuration_mismatch')
    if (number(policy.get('admission_free_ram_mib')) and number(policy.get('runtime_free_ram_floor_mib'))
            and policy['admission_free_ram_mib'] < policy['runtime_free_ram_floor_mib']):
        errors.append('admission_below_runtime_floor')
    if any(k in sample for k in ('gpu_error', 'free_ram_error', 'commit_error', 'api_error', 'process_error')):
        errors.append('telemetry_error')
    gpu = sample.get('gpu') or {}
    commit = sample.get('commit') or {}
    if not number(sample.get('free_ram_mib')): errors.append('missing_free_ram_mib')
    if not isinstance(sample.get('api_version'),dict) or not sample['api_version'].get('version'): errors.append('missing_api_version')
    if not isinstance(sample.get('running_models'),list): errors.append('missing_running_models')
    if not number(commit.get('commit_headroom_mib')): errors.append('missing_commit_headroom')
    if not all(number(gpu.get(k)) for k in ('temperature_c','vram_used_mib','vram_total_mib')):
        errors.append('missing_gpu_telemetry')
    elif gpu['vram_total_mib'] <= 0 or gpu['vram_used_mib'] > gpu['vram_total_mib']:
        errors.append('invalid_vram_telemetry')
    if gpu.get('hw_thermal_slowdown') != 'Not Active' or gpu.get('sw_thermal_slowdown') != 'Not Active':
        errors.append('thermal_slowdown_or_unavailable')
    if isinstance(gpu.get('temperature_c'), (int,float)) and gpu['temperature_c'] >= policy.get('local_gpu_stop_c', 82):
        errors.append('local_gpu_stop')
    if admission and sample.get('running_models'): errors.append('other_loaded_model')
    def below(value, threshold, label):
        if number(value) and number(threshold) and value < threshold:
            errors.append(label)
    below(sample.get('free_ram_mib'), policy.get('admission_free_ram_mib' if admission else 'runtime_free_ram_floor_mib'), 'ram_below_profile_limit')
    below(commit.get('commit_headroom_mib'), policy.get('minimum_commit_headroom_mib'), 'commit_below_profile_limit')
    if isinstance(gpu.get('vram_total_mib'),(int,float)) and isinstance(gpu.get('vram_used_mib'),(int,float)):
        below(gpu['vram_total_mib']-gpu['vram_used_mib'],policy.get('minimum_free_vram_mib'),'vram_below_profile_limit')
    return list(dict.fromkeys(errors))
