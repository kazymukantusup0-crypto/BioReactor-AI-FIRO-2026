"""One opted-in Qwen 4B probe, gated by its own fail-closed policy."""
import json
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'evaluations'))
import qwen_offload_ab_harness as telemetry
from qwen3_4b_resource_policy import load_policy, reasons
from src.agent.cancellation import CancellationSignal
from src.agent.providers import request_json

MODEL = 'qwen3:4b-q4_K_M'
RESULT = ROOT / 'reports' / f'qwen3_4b_controlled_probe_{time.time_ns()}.json'


def main():
    policy = load_policy()
    result = {'model': MODEL, 'status': 'RUNNING', 'samples': [], 'events': [],
              'resource_policy': policy,
              'gpu_stop_c': telemetry.GPU_STOP_C, 'timeout_seconds': 120,
              'runtime': 'shared Ollama API; one probe request from this script',
              'other_clients_concurrency': 'not controlled'}
    signal = CancellationSignal()
    signal.set_stream_observer(result['events'].append)
    start = time.monotonic()
    body = {'model': MODEL, 'stream': True, 'think': False, 'keep_alive': 0,
            'messages': [{'role': 'user', 'content': 'Кратко объясни, что такое BMP.'}],
            'options': {'num_ctx': 4096, 'num_batch': 32, 'num_gpu': -1, 'num_predict': 80}}
    def invoke():
        try:
            result['response'] = request_json('http://127.0.0.1:11434/api/chat', body, 120, cancellation=signal)
        except Exception as exc:
            result['error'] = f'{type(exc).__name__}: {exc}'
    initial = telemetry.sample(0)
    result['initial'] = initial
    admission_reasons = reasons(initial, policy, admission=True)
    if admission_reasons:
        result.update(status='BLOCKED', reasons=admission_reasons)
        RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'status':'BLOCKED','reasons':admission_reasons}))
        return
    worker = threading.Thread(target=invoke, daemon=True)
    worker.start()
    while worker.is_alive():
        row = telemetry.sample(len(result['samples']) + 1)
        result['samples'].append(row)
        failures = reasons(row, policy, admission=False)
        reason = ', '.join(failures) if failures else None
        if time.monotonic() - start >= 120: reason = 'request timeout'
        if reason:
            result['stop_reason'] = reason
            signal.cancel()
            break
        worker.join(1)
    worker.join(10)
    result['worker_stopped'] = not worker.is_alive()
    result['elapsed_seconds'] = round(time.monotonic() - start, 2)
    result['status'] = 'COMPLETED' if not worker.is_alive() and 'response' in result and not signal.cancelled else 'STOPPED_OR_FAILED'
    result['final'] = telemetry.sample(999)
    RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k not in ('samples','events')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
