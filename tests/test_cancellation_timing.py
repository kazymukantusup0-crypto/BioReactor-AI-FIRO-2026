import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
import json

from evaluations.cancellation_timing import CancellationTimingProbe
from src.agent.cancellation import CancellationSignal, ExecutionStopped
from src.agent.providers import request_json


def event(event_type, when, **fields):
    return {
        'type': event_type,
        'timestamp_utc': f'2026-11-09T00:00:{when:02d}+00:00',
        'timestamp_monotonic': float(when),
        **fields,
    }


def test_cancel_is_sent_once_after_first_live_content_while_stream_is_open():
    peer_closed = threading.Event()
    cancel_http_received = threading.Event()
    second_chunk_sent = []
    outcome = []
    signal = CancellationSignal()
    cancel_http_count = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path == '/api/dashboard/jobs/job-1/cancel':
                self.rfile.read(int(self.headers.get('Content-Length', '0')))
                cancel_http_count.append(self.path)
                signal.cancel()
                body = json.dumps({'status': 'RUNNING', 'cancel_requested': True}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                cancel_http_received.set()
                return
            self.rfile.read(int(self.headers.get('Content-Length', '0')))
            self.send_response(200)
            self.send_header('Content-Type', 'application/x-ndjson')
            self.end_headers()
            self.wfile.write(b'{"message":{"content":"first-token"},"done":false}\n')
            self.wfile.flush()
            self.connection.settimeout(2)
            try:
                self.connection.recv(1)
            except OSError:
                pass
            peer_closed.set()
            second_chunk_sent.append(False)
        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    probe = CancellationTimingProbe(timeout_seconds=5)
    def send_cancel():
        request = Request(f'http://127.0.0.1:{server.server_port}/api/dashboard/jobs/job-1/cancel',
                          data=b'{}', headers={'Content-Type': 'application/json'}, method='POST')
        with urlopen(request, timeout=2) as response:
            return {'http_status': response.status, 'job': json.loads(response.read())}
    probe.bind('job-1', send_cancel, safe_cancel=signal.cancel)
    signal.set_stream_observer(probe.on_provider_event)

    def invoke():
        try:
            request_json(f'http://127.0.0.1:{server.server_port}/stream',
                         {'stream': True}, timeout=3, cancellation=signal)
            outcome.append('returned')
        except Exception as exc:
            outcome.append(exc)

    thread = threading.Thread(target=invoke, daemon=True)
    thread.start()
    try:
        thread.join(3)
        assert not thread.is_alive()
        assert peer_closed.wait(1)
        assert cancel_http_received.wait(1)
        assert outcome and isinstance(outcome[0], ExecutionStopped)
        assert cancel_http_count == ['/api/dashboard/jobs/job-1/cancel']
        snapshot = probe.snapshot()
        names = [item['event'] for item in snapshot['events']]
        assert names.index('stream_content') < names.index('cancel_request_started')
        assert 'transport_closed' in names and 'request_closed' in names
        assert 'stream_done' not in names
        assert second_chunk_sent == [False]
    finally:
        server.shutdown();server.server_close();server_thread.join(1)


def test_natural_stream_completion_does_not_send_cancel():
    now = [100.0]
    sent = []
    probe = CancellationTimingProbe(5, monotonic=lambda: now[0], utc_now=lambda: '2026-11-09T00:00:00+00:00')
    probe.bind('job-natural', lambda: sent.append(True) or {'http_status': 200, 'job': {'cancel_requested': True}})
    probe.on_provider_event(event('stream_done', 1, sequence=1, done=True))
    assert probe.snapshot()['status'] == 'NATURAL_DONE'
    assert probe.snapshot()['cancel_attempted'] is False
    assert sent == []


def test_absent_generation_signal_expires_with_one_bounded_cleanup_cancel():
    sent = []
    probe = CancellationTimingProbe(timeout_seconds=1)
    probe.bind('job-timeout', lambda: (sent.append(time.monotonic()) or {
        'http_status': 200, 'job': {'status': 'RUNNING', 'cancel_requested': True}}))
    started = time.monotonic()
    result = probe.wait()
    elapsed = time.monotonic() - started
    assert elapsed <= 1.5
    assert result['status'] == 'INCONCLUSIVE'
    assert result['cancel_attempted'] is True
    assert len(sent) == 1
    classification = probe.finalize({'telemetry_ok': True})
    assert classification['status'] == 'INCONCLUSIVE'
    assert classification['status'] != 'VERIFIED'


def test_telemetry_failure_blocks_and_safely_cancels_once():
    calls = []
    emergency = []
    probe = CancellationTimingProbe(5)
    probe.bind('job-telemetry', lambda: (calls.append('http') or {
        'http_status': 200, 'job': {'status': 'RUNNING', 'cancel_requested': True}}),
        safe_cancel=lambda: emergency.append('closed'))
    probe.telemetry_failure('stream observer failed')
    assert probe.snapshot()['status'] == 'BLOCKED'
    assert calls == ['http']
    assert emergency == []
    assert probe.finalize({'telemetry_ok': False})['status'] == 'BLOCKED'


def test_unexpected_observer_exception_becomes_blocked_without_escaping():
    probe = CancellationTimingProbe(5)
    probe.bind('job-observer-error', lambda: {'http_status': 200,
                                               'job': {'status': 'RUNNING', 'cancel_requested': True}})
    probe.on_provider_event = lambda _event: (_ for _ in ()).throw(RuntimeError('observer failure'))
    probe.guarded_provider_observer({'type': 'stream_content'})
    assert probe.snapshot()['status'] == 'BLOCKED'
    assert probe.snapshot()['telemetry_error'] == 'RuntimeError'


def test_repeated_content_events_never_send_duplicate_cancel():
    calls = []
    probe = CancellationTimingProbe(5, monotonic=lambda: 100.0, utc_now=lambda: '2026-11-09T00:00:00+00:00')
    probe.bind('job-repeat', lambda: (calls.append(1) or {
        'http_status': 200, 'job': {'status': 'RUNNING', 'cancel_requested': True}}))
    probe.on_provider_event(event('stream_content', 1, sequence=1, content_characters=4, done=False))
    probe.on_provider_event(event('stream_content', 2, sequence=2, content_characters=5, done=False))
    assert calls == [1]
    assert probe.snapshot()['cancel_attempted'] is True


def test_rejected_cancel_attempt_safely_closes_and_cannot_verify():
    emergency = []
    probe = CancellationTimingProbe(5, monotonic=lambda: 10.0, utc_now=lambda: '2026-11-09T00:00:00+00:00')
    probe.bind('job-rejected', lambda: {'http_status': 200, 'job': {'status': 'COMPLETED', 'cancel_requested': False}},
               safe_cancel=lambda: emergency.append('closed'))
    probe.on_provider_event(event('stream_content', 1, sequence=1, content_characters=2, done=False))
    assert probe.snapshot()['status'] == 'CANCEL_REJECTED'
    assert emergency == ['closed']
    assert probe.finalize({'telemetry_ok': True})['status'] == 'INCONCLUSIVE'


def test_provider_timestamps_are_preserved_and_ordered_around_cancel():
    clock = [200.0]
    probe = CancellationTimingProbe(10, monotonic=lambda: clock[0], utc_now=lambda: '2026-11-09T00:00:00+00:00')
    def sender():
        clock[0] = 203.0
        probe.on_provider_event(event('transport_closed', 4, timestamp_monotonic=203.5, reason='cancelled'))
        return {'http_status': 200, 'job': {'status': 'RUNNING', 'cancel_requested': True}}
    probe.bind('job-times', sender)
    clock[0] = 201.0
    probe.on_provider_event(event('stream_content', 1, timestamp_monotonic=200.9,
                                  sequence=1, content_characters=3, done=False))
    clock[0] = 204.0
    probe.on_provider_event(event('request_closed', 5, timestamp_monotonic=205.0, reason='cancelled'))
    snapshot = probe.snapshot()
    content = next(item for item in snapshot['events'] if item['event'] == 'stream_content')
    start = next(item for item in snapshot['events'] if item['event'] == 'cancel_request_started')
    closed = next(item for item in snapshot['events'] if item['event'] == 'transport_closed')
    assert content['timestamp_utc'] == '2026-11-09T00:00:01+00:00'
    assert content['timestamp_monotonic'] == 200.9
    assert content['timestamp_monotonic'] <= start['timestamp_monotonic'] < closed['timestamp_monotonic']


def test_verified_requires_every_external_and_transport_fact():
    clock = [0.0]
    probe = CancellationTimingProbe(10, monotonic=lambda: clock[0], utc_now=lambda: '2026-11-09T00:00:00+00:00')
    def sender():
        clock[0] = 3.0
        probe.on_provider_event(event('transport_closed', 3, reason='cancelled'))
        return {'http_status': 200, 'job': {'status': 'RUNNING', 'cancel_requested': True}}
    probe.bind('job-evidence', sender)
    clock[0] = 1.0
    probe.on_provider_event(event('stream_content', 1, sequence=1, content_characters=2, done=False))
    probe.on_provider_event(event('request_closed', 4, reason='cancelled'))
    required_evidence = {
        'telemetry_ok': True, 'job_status': 'CANCELLED', 'reply_present': False,
        'state_version_before': 0, 'state_version_after': 0,
        'slot_released_after_cancel': True, 'ollama_progress_after_cancel': False,
        'normal_completion_logged': False,
    }
    assert probe.finalize(required_evidence)['status'] == 'VERIFIED'
    for missing in required_evidence:
        incomplete = dict(required_evidence)
        incomplete.pop(missing)
        assert probe.finalize(incomplete)['status'] != 'VERIFIED', missing
    assert probe.finalize({**required_evidence, 'ollama_progress_after_cancel': True})['status'] == 'FAILED'


def test_late_terminal_observation_prevents_timeout_cancel():
    now = [0.0]
    sent = []
    probe = CancellationTimingProbe(1, monotonic=lambda: now[0], utc_now=lambda: '2026-11-09T00:00:00+00:00')
    probe.bind('job-completed', lambda: sent.append(True) or {'http_status': 200, 'job': {'cancel_requested': True}})
    assert probe.observe_job_terminal('COMPLETED') is True
    now[0] = 2.0
    assert probe.expire() is False
    assert sent == []
    assert probe.snapshot()['status'] == 'NATURAL_DONE'
