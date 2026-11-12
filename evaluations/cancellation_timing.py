"""Conservative evidence collector for one isolated live Ollama cancellation run."""
from __future__ import annotations

from datetime import datetime, timezone
import math
import threading
import time
from typing import Callable


MAX_TIMEOUT_SECONDS = 120.0


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CancellationTimingProbe:
    """Trigger one Dashboard Cancel on the first live, nonterminal content chunk.

    Provider events carry their own UTC and monotonic receive times. Cancel is
    claimed under a lock before network I/O, so repeated chunks cannot issue a
    second request. Missing/ambiguous evidence is never promoted to VERIFIED.
    """

    def __init__(self, timeout_seconds=45.0, *, monotonic=time.monotonic,
                 utc_now: Callable[[], str] = _utc_now):
        timeout = float(timeout_seconds)
        if not math.isfinite(timeout) or not 1.0 <= timeout <= MAX_TIMEOUT_SECONDS:
            raise ValueError(f'timeout_seconds must be in 1..{MAX_TIMEOUT_SECONDS:g}')
        self.timeout_seconds = timeout
        self._monotonic = monotonic
        self._utc_now = utc_now
        self.armed_at = monotonic()
        self.deadline = self.armed_at + timeout
        self._lock = threading.RLock()
        self._wake = threading.Event()
        self._cancel_sender = None
        self._safe_cancel = None
        self._cancel_claimed = False
        self._cancel_accepted = False
        self._cancel_started = None
        self._status = 'ARMED'
        self._job_id = None
        self._events = []
        self._telemetry_error = None

    def bind(self, job_id, cancel_sender, safe_cancel=None):
        with self._lock:
            if self._job_id is not None:
                raise RuntimeError('probe is already bound to a job')
            self._job_id = str(job_id)
            self._cancel_sender = cancel_sender
            self._safe_cancel = safe_cancel
            self._record_locked('job_bound', {'job_id': self._job_id})

    def _record_locked(self, name, fields=None, *, timestamp_utc=None, timestamp_monotonic=None):
        self._events.append({
            'event': name,
            'timestamp_utc': timestamp_utc or self._utc_now(),
            'timestamp_monotonic': self._monotonic() if timestamp_monotonic is None else timestamp_monotonic,
            **(fields or {}),
        })

    def _claim_cancel_locked(self, reason):
        if self._cancel_claimed or self._cancel_sender is None:
            return None
        self._cancel_claimed = True
        self._cancel_started = self._monotonic()
        self._record_locked('cancel_request_started', {'reason': reason})
        return self._cancel_sender

    def _send_cancel(self, sender, reason):
        if sender is None:
            return
        try:
            response = sender()
            if not isinstance(response, dict):
                raise TypeError('Cancel sender must return a response dictionary')
            http_status = response.get('http_status')
            job = response.get('job') if isinstance(response.get('job'), dict) else response
            accepted = http_status == 200 and (
                job.get('status') == 'CANCELLED' or job.get('cancel_requested') is True
            )
            with self._lock:
                self._cancel_accepted = bool(accepted)
                self._record_locked('cancel_response', {
                    'reason': reason, 'http_status': http_status,
                    'job_status': job.get('status'),
                    'cancel_requested': job.get('cancel_requested'),
                    'accepted': bool(accepted),
                })
                if accepted and reason == 'first_live_content':
                    self._status = 'CANCEL_SENT'
                elif not accepted and self._status not in {'BLOCKED', 'INCONCLUSIVE'}:
                    self._status = 'CANCEL_REJECTED'
                self._wake.set()
            if not accepted:
                self._emergency_cancel()
        except Exception as exc:
            with self._lock:
                self._record_locked('cancel_error', {'reason': reason, 'error_type': type(exc).__name__})
                self._status = 'BLOCKED'
                self._wake.set()
            self._emergency_cancel()

    def _emergency_cancel(self):
        with self._lock:
            callback = self._safe_cancel
        if callback is not None:
            try:
                callback()
            except Exception:
                pass

    def on_provider_event(self, event):
        """Receive an event emitted synchronously while the provider reads NDJSON."""
        try:
            event_type = event.get('type')
            timestamp_utc = event['timestamp_utc']
            timestamp_monotonic = float(event['timestamp_monotonic'])
            if not math.isfinite(timestamp_monotonic) or not isinstance(timestamp_utc, str):
                raise ValueError('invalid event timestamp')
            datetime.fromisoformat(timestamp_utc.replace('Z', '+00:00'))
            if event_type not in {'stream_content', 'stream_done', 'transport_closed', 'request_closed'}:
                raise ValueError('unknown provider event')
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            self.telemetry_failure(type(exc).__name__)
            return

        sender = None
        reason = 'first_live_content'
        with self._lock:
            safe_fields = {key: event[key] for key in ('sequence', 'content_characters', 'done', 'reason') if key in event}
            self._record_locked(event_type, safe_fields, timestamp_utc=timestamp_utc,
                                timestamp_monotonic=timestamp_monotonic)

            if event_type == 'stream_done':
                if not self._cancel_claimed:
                    self._status = 'NATURAL_DONE'
                self._wake.set()
                return

            if event_type == 'stream_content':
                sequence = event.get('sequence')
                characters = event.get('content_characters')
                if (isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1
                        or isinstance(characters, bool) or not isinstance(characters, int) or characters < 1
                        or event.get('done') is not False):
                    invalid = True
                else:
                    invalid = False
                if invalid:
                    # Leave the lock before invoking the failure path.
                    pass
                elif not self._cancel_claimed and self._status == 'ARMED':
                    if self._monotonic() >= self.deadline:
                        self._status = 'INCONCLUSIVE'
                        self._record_locked('generation_signal_after_deadline')
                        sender = self._claim_cancel_locked('timeout_cleanup')
                        reason = 'timeout_cleanup'
                    else:
                        self._status = 'GENERATION_OBSERVED'
                        self._record_locked('generation_signal_accepted', {
                            'sequence': sequence, 'content_characters': characters,
                        }, timestamp_utc=timestamp_utc, timestamp_monotonic=timestamp_monotonic)
                        sender = self._claim_cancel_locked('first_live_content')
                self._wake.set()
            elif event_type == 'transport_closed' and event.get('reason') != 'cancelled':
                # An ordinary close is not evidence that the Cancel path closed the socket.
                self._wake.set()

        if event_type == 'stream_content' and invalid:
            self.telemetry_failure('invalid_stream_content_event')
            return
        if sender is not None:
            self._send_cancel(sender, reason)

    def guarded_provider_observer(self, event):
        """Turn unexpected observer/telemetry exceptions into BLOCKED plus safe cancel."""
        try:
            self.on_provider_event(event)
        except Exception as exc:
            self.telemetry_failure(type(exc).__name__)

    def telemetry_failure(self, detail):
        with self._lock:
            self._telemetry_error = str(detail)[:120]
            self._status = 'BLOCKED'
            self._record_locked('telemetry_error', {'detail': self._telemetry_error})
            sender = self._claim_cancel_locked('telemetry_failure')
            self._wake.set()
        if sender is not None:
            self._send_cancel(sender, 'telemetry_failure')
        else:
            self._emergency_cancel()

    def expire(self):
        """Expire the one-shot wait; issue at most one safety Cancel if still armed."""
        sender = None
        with self._lock:
            if self._monotonic() < self.deadline or self._status not in {'ARMED'}:
                return False
            self._status = 'INCONCLUSIVE'
            self._record_locked('generation_signal_timeout', {'timeout_seconds': self.timeout_seconds})
            sender = self._claim_cancel_locked('timeout_cleanup')
            self._wake.set()
        if sender is not None:
            self._send_cancel(sender, 'timeout_cleanup')
        return True

    def observe_job_terminal(self, status):
        """Record external job completion so timeout cleanup cannot cancel a finished job."""
        with self._lock:
            if status not in {'COMPLETED', 'FAILED', 'CANCELLED', 'TIMED_OUT'}:
                return False
            if self._cancel_claimed or self._status != 'ARMED':
                return False
            self._status = 'NATURAL_DONE' if status == 'COMPLETED' else 'INCONCLUSIVE'
            self._record_locked('job_terminal_before_generation_signal', {'job_status': status})
            self._wake.set()
            return True

    def wait(self):
        """Wait no longer than the configured deadline for signal or natural completion."""
        while True:
            with self._lock:
                if self._status != 'ARMED':
                    break
                remaining = self.deadline - self._monotonic()
                if remaining <= 0:
                    break
            self._wake.wait(remaining)
            self._wake.clear()
        self.expire()
        return self.snapshot()

    def snapshot(self):
        with self._lock:
            return {
                'status': self._status,
                'job_id': self._job_id,
                'timeout_seconds': self.timeout_seconds,
                'deadline_monotonic': self.deadline,
                'cancel_attempted': self._cancel_claimed,
                'cancel_accepted': self._cancel_accepted,
                'telemetry_error': self._telemetry_error,
                'events': [dict(event) for event in self._events],
            }

    def finalize(self, evidence):
        """Classify only from the complete, explicit evidence needed for VERIFIED."""
        if not isinstance(evidence, dict):
            raise TypeError('evidence must be a dictionary')
        with self._lock:
            events = [dict(item) for item in self._events]
            status = self._status
            cancel_accepted = self._cancel_accepted
            cancel_started = self._cancel_started
            telemetry_error = self._telemetry_error
        if telemetry_error or evidence.get('telemetry_ok') is False:
            return {'status': 'BLOCKED', 'reasons': ['telemetry_failure'], 'events': events}

        post_cancel = [event for event in events if cancel_started is not None
                       and event['timestamp_monotonic'] > cancel_started
                       and event['event'] in {'stream_content', 'stream_done'}]
        if post_cancel or evidence.get('ollama_progress_after_cancel') is True or evidence.get('normal_completion_logged') is True:
            return {'status': 'FAILED', 'reasons': ['generation_or_normal_completion_observed_after_cancel'], 'events': events}

        by_name = {}
        for event in events:
            by_name.setdefault(event['event'], []).append(event)
        generation_event = next(iter(by_name.get('generation_signal_accepted', [])), None)
        cancel_start_event = next(iter(by_name.get('cancel_request_started', [])), None)
        generation = bool(generation_event and cancel_start_event
                          and generation_event['timestamp_monotonic'] <= cancel_start_event['timestamp_monotonic'])
        cancel_start = bool(cancel_start_event)
        closed = any(item.get('reason') == 'cancelled' and cancel_started is not None
                     and item['timestamp_monotonic'] >= cancel_started
                     for item in by_name.get('transport_closed', []))
        request_closed_cancelled = any(item.get('reason') == 'cancelled'
                                       for item in by_name.get('request_closed', []))
        required = {
            'telemetry_ok': evidence.get('telemetry_ok') is True,
            'probe_confirmed_cancel_sent': status == 'CANCEL_SENT',
            'generation_signal_before_cancel': generation and cancel_start,
            'cancel_accepted': cancel_accepted,
            'transport_closed_after_cancel': closed,
            'provider_request_closed_as_cancelled': request_closed_cancelled,
            'job_cancelled': evidence.get('job_status') == 'CANCELLED',
            'no_reply_saved': evidence.get('reply_present') is False,
            'state_unchanged': (isinstance(evidence.get('state_version_before'), int)
                                and not isinstance(evidence.get('state_version_before'), bool)
                                and evidence.get('state_version_after') == evidence.get('state_version_before')),
            'ollama_slot_released': evidence.get('slot_released_after_cancel') is True,
            'no_ollama_progress_after_cancel': evidence.get('ollama_progress_after_cancel') is False,
            'no_normal_completion': evidence.get('normal_completion_logged') is False,
        }
        if status == 'BLOCKED':
            return {'status': 'BLOCKED', 'reasons': ['probe_blocked'], 'requirements': required, 'events': events}
        if all(required.values()):
            return {'status': 'VERIFIED', 'reasons': [], 'requirements': required, 'events': events}
        return {'status': 'INCONCLUSIVE', 'reasons': [name for name, passed in required.items() if not passed],
                'requirements': required, 'events': events}
