"""Sequential live FastAPI job checks using the real local Ollama provider."""
import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'evaluations'))
import qwen_offload_ab_harness as telemetry
from qwen3_4b_resource_policy import load_policy, reasons
from qwen3_4b_agent_qa import Qwen4BQAProvider
from src.agent.providers import HybridLLM
from src.market.api import create_app
from src.market.store import Store
from fastapi.testclient import TestClient

OUT = ROOT / 'reports' / f'qwen3_4b_live_chat_{time.time_ns()}.json'
PROMPTS = [
    'Нужен ли кислород метаногенам при анаэробном сбраживании? Объясни.',
    'Чем лабораторный BMP отличается от теоретического максимума метана?',
    'Рассчитай 0,6 кг VS при BMP 250 мл CH₄/г VS. Сколько литров метана?',
    'У меня 142 л коровьего навоза и реактор 200 л. Сколько метана получится за 30 дней?',
    'Исправление: не 142, а 160 литров навоза.',
]


def main():
    policy = load_policy()
    out = {'status': 'RUNNING', 'cases': [], 'requests': [], 'resource_policy': policy,
           'provider': 'real qwen3:4b-q4_K_M via Ollama 127.0.0.1:11434',
           'endpoint': '/api/dashboard/chat/sessions/{id}/jobs', 'production_config_changed': False}
    def save(): OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    class RealProvider(Qwen4BQAProvider):
        def __init__(self):
            super().__init__()
            self.url = 'http://127.0.0.1:11434/api/chat'
        def generate(self, messages, schema=None):
            item = {'started': telemetry.now()}
            out['requests'].append(item)
            try:
                response = super().generate(messages, schema)
                item.update(status='returned', finished=telemetry.now())
                return response
            except Exception as exc:
                item.update(status='error', error=f'{type(exc).__name__}: {exc}', finished=telemetry.now())
                raise
    def factory(*args, **kwargs):
        return HybridLLM('offline', providers=[RealProvider()], strict_model=True)
    with tempfile.TemporaryDirectory(dir=ROOT, prefix='.tmp-qwen4b-live-') as tmp:
        app = create_app(Store(Path(tmp) / 'qa.sqlite3'), scheduler_enabled=False)
        with patch('src.dashboard.api.HybridLLM', side_effect=factory), TestClient(app) as client:
            session = None
            for i, prompt in enumerate(PROMPTS):
                before = telemetry.sample(0)
                failures = reasons(before, policy, admission=True)
                if failures:
                    out['stop_reason'] = 'admission blocked: ' + ', '.join(failures); break
                if i != 4:
                    session = client.post('/api/dashboard/chat/sessions', json={'mode':'offline','context':{},'conversation_version':'7'}).json()
                    version = 0
                item = {'prompt':prompt, 'started':telemetry.now(), 'samples':[], 'request_count_before':len(out['requests'])}
                out['cases'].append(item); save()
                accepted = client.post(f"/api/dashboard/chat/sessions/{session['id']}/jobs", json={
                    'message':prompt, 'request_id':f'Q4B_LIVE_{i}', 'expected_state_version':version})
                item['http_status'] = accepted.status_code
                if accepted.status_code != 202:
                    item['error'] = accepted.text; out['stop_reason'] = 'job submission error'; break
                jobid = accepted.json()['id']; start = time.monotonic()
                while True:
                    job = client.get(f'/api/dashboard/jobs/{jobid}').json()
                    if job.get('terminal'): break
                    sample = telemetry.sample(len(item['samples'])+1); item['samples'].append(sample)
                    failures = reasons(sample, policy, admission=False)
                    reason = ', '.join(failures) if failures else None
                    if time.monotonic()-start > 120: reason = 'job timeout'
                    if reason:
                        item['cancel_response'] = client.post(f'/api/dashboard/jobs/{jobid}/cancel').json()
                        item['stop_reason'] = out['stop_reason'] = reason
                        break
                    time.sleep(1)
                item['elapsed_seconds'] = round(time.monotonic()-start,2)
                item['job'] = job
                item['request_count_after'] = len(out['requests'])
                if not item.get('stop_reason') and job.get('status') == 'COMPLETED':
                    item['result'] = client.get(job['result_reference']).json()
                    version = item['result']['reply']['state_version']
                else:
                    out.setdefault('stop_reason', f"job ended {job.get('status')}")
                item['finished'] = telemetry.now(); save()
                if out.get('stop_reason'): break
    out['final_sample'] = telemetry.sample(999)
    out['status'] = 'STOPPED' if out.get('stop_reason') else 'COMPLETED'
    save()
    print(json.dumps({'status':out['status'],'stop_reason':out.get('stop_reason'),'cases':len(out['cases']), 'real_requests':len(out['requests'])}, ensure_ascii=False))


if __name__ == '__main__': main()
