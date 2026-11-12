"""Experimental safety policy regressions; does not call Ollama."""
from copy import deepcopy
from pathlib import Path

import pytest
from evaluations.qwen3_4b_resource_policy import FIELDS, load_policy, reasons
from evaluations.qwen3_4b_agent_qa import Qwen4BQAProvider


def sample():
    return {'free_ram_mib': 7000, 'commit': {'commit_headroom_mib': 20000},
            'gpu': {'temperature_c': 56, 'vram_total_mib': 8192, 'vram_used_mib': 500,
                    'hw_thermal_slowdown': 'Not Active', 'sw_thermal_slowdown': 'Not Active'},
            'api_version': {'version':'0.40.16'}, 'running_models': []}


def artificial_policy():
    # Synthetic numbers exercise comparison logic; they do not authorize a run.
    return {'model':'qwen3:4b-q4_K_M','status':'APPROVED_FOR_EXPERIMENT',
            'justification':'TEST ONLY', 'local_gpu_stop_c':82,
            'request':{'num_ctx':4096,'num_batch':32,'num_gpu':-1,'parallel':1,'keep_alive':0},
            **{name: 100 for name in FIELDS}}


def test_real_policy_does_not_inherit_8b_and_remains_blocked():
    policy = load_policy()
    assert policy['runtime_free_ram_floor_mib'] is None
    assert 'policy_not_admitted' in reasons(sample(), policy, admission=True)
    assert 'unestablished_runtime_free_ram_floor_mib' in reasons(sample(), policy, admission=False)


@pytest.mark.parametrize('field', FIELDS)
def test_unknown_profile_bound_blocks(field):
    policy = artificial_policy(); policy[field] = None
    assert 'unestablished_'+field in reasons(sample(),policy,admission=True)


def test_policy_checks_runtime_ram_thermal_telemetry_and_model_conflicts():
    policy = artificial_policy(); row = sample()
    assert not reasons(row,policy,admission=True)
    row['free_ram_mib'] = 99
    row['gpu']['hw_thermal_slowdown'] = 'Active'
    row['running_models'] = [{'name':'other'}]
    row['commit_error'] = 'missing'
    result = reasons(row,policy,admission=True)
    assert {'ram_below_profile_limit','thermal_slowdown_or_unavailable','other_loaded_model','telemetry_error'} <= set(result)


def test_qa_provider_supplies_scientific_context_without_modifying_config():
    path = Path('data/config/llm_selection.json'); before = path.read_bytes()
    provider = Qwen4BQAProvider()
    payload = provider.payload([{'role':'user','content':'Что такое BMP?'}])
    assert 'biochemical methane potential' in payload['messages'][0]['content']
    assert 'bitmap image' in payload['messages'][0]['content']
    assert payload['messages'][-1]['content'] == 'Что такое BMP?'
    assert path.read_bytes() == before
