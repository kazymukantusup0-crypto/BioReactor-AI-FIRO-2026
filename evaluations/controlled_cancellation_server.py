"""Opt-in QA wrapper that cancels one isolated job on its first live content chunk.

Run only with an explicit temporary BIOREACTOR_QA_DB. This wrapper is separate
from the product routes and is intentionally not started by the application.
"""
import json
import os
import sys
import threading
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if not os.getenv('BIOREACTOR_QA_DB'):
    raise RuntimeError('Set BIOREACTOR_QA_DB to a new temporary SQLite path before starting this QA server.')

from evaluations.reliability_qwen_server import app
from evaluations.cancellation_timing import CancellationTimingProbe
from fastapi import HTTPException

runtime = app.state.agent_runtime
port = int(os.getenv('BIOREACTOR_CANCEL_QA_PORT', '8775'))
base_url = f'http://127.0.0.1:{port}'
_lock = threading.Lock()
_armed = None


def _send_dashboard_cancel(job_id):
    request = Request(
        f'{base_url}/api/dashboard/jobs/{job_id}/cancel',
        data=b'{}', headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urlopen(request, timeout=3.0) as response:
            raw = response.read(64 * 1024)
            return {'http_status': response.status, 'job': json.loads(raw)}
    except HTTPError as exc:
        raw = exc.read(64 * 1024)
        return {'http_status': exc.code, 'job': json.loads(raw) if raw else {}}
    except (OSError, URLError, TimeoutError) as exc:
        raise RuntimeError(f'Cancel API transport failed: {type(exc).__name__}') from None


def _observer_factory(job, signal):
    global _armed
    with _lock:
        current = _armed
        if current is None or current['bound']:
            return None
        current['bound'] = True
        probe = current['probe']
    probe.bind(job['id'], lambda: _send_dashboard_cancel(job['id']), safe_cancel=signal.cancel)
    return probe.guarded_provider_observer


runtime.stream_observer_factory = _observer_factory


@app.post('/__qa/cancellation/arm')
def arm(body: dict):
    global _armed
    timeout = body.get('timeout_seconds', 45)
    with runtime.store.connect() as con:
        active = con.execute("SELECT id,status FROM agent_jobs WHERE status IN ('QUEUED','RUNNING','TOOL_EXECUTION','FINALIZING') LIMIT 1").fetchone()
    if active:
        raise HTTPException(409, 'An existing QA job is active; use a fresh isolated database.')
    with _lock:
        if _armed is not None and _armed['probe'].snapshot()['status'] in {'ARMED', 'GENERATION_OBSERVED', 'CANCEL_SENT'}:
            raise HTTPException(409, 'A cancellation probe is already active.')
        probe = CancellationTimingProbe(timeout_seconds=timeout)
        _armed = {'probe': probe, 'bound': False}
    return probe.snapshot()


def _current_probe():
    with _lock:
        return _armed['probe'] if _armed else None


@app.get('/__qa/cancellation/status')
def status():
    probe = _current_probe()
    if probe is None:
        raise HTTPException(404, 'No cancellation probe has been armed.')
    snapshot = probe.snapshot()
    job_id = snapshot.get('job_id')
    if job_id:
        job = runtime.get(job_id)
        if job['terminal']:
            probe.observe_job_terminal(job['status'])
    probe.expire()
    return probe.snapshot()


@app.post('/__qa/cancellation/finalize')
def finalize(evidence: dict):
    probe = _current_probe()
    if probe is None:
        raise HTTPException(404, 'No cancellation probe has been armed.')
    snapshot = probe.snapshot()
    job_id = snapshot.get('job_id')
    if job_id:
        job = runtime.get(job_id)
        evidence.setdefault('job_status', job['status'])
        evidence.setdefault('reply_present', job['reply'] is not None)
    return probe.finalize(evidence)


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=port, log_level='info')
