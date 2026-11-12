"""Offline checks only: no GPU telemetry, Ollama inference or server mutation."""
import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('qwen3_4b_compact_plan',ROOT/'evaluations/qwen3_4b_compact_plan.py')
plan=importlib.util.module_from_spec(spec)
spec.loader.exec_module(plan)

def test_profile_is_correct_and_fails_closed_when_resource_bounds_unknown():
    result=plan.inspect();body=result['request_preview']
    assert result['status']=='BLOCKED'
    assert result['inference']=='NOT RUN' and result['telemetry']=='NOT RUN'
    assert 'runner_job_containment_verified' in result['missing_evidence']
    assert body['model']=='qwen3:4b-q4_K_M' and body['keep_alive']==0
    assert body['options']['num_ctx']==2048 and body['options']['num_batch']==16
    assert result['unicode']=='PASS'

def test_profile_validation_never_exposes_a_live_execution_entrypoint():
    assert not hasattr(plan,'run')
