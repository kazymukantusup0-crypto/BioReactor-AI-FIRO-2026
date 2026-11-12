"""Job-scoped cancellation primitives shared by agent and dashboard layers."""
import logging
import threading


class ExecutionStopped(Exception):
    """An execution was cancelled, timed out, or lost its ownership fence."""


class CancellationSignal:
    """Thread-safe cancellation event with callbacks for active I/O handles."""

    def __init__(self):
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._callbacks = {}
        self._next_callback = 0
        self._stream_observer = None

    def set_stream_observer(self, observer):
        """Install an optional per-job observer, primarily for isolated QA runs."""
        with self._lock:
            self._stream_observer = observer

    @property
    def has_stream_observer(self):
        with self._lock:
            return self._stream_observer is not None

    def emit_stream_event(self, event):
        """Report an already received provider-stream event without holding the lock."""
        with self._lock:
            observer = self._stream_observer
        if observer is not None:
            observer(dict(event))

    @property
    def cancelled(self):
        return self._event.is_set()

    def throw_if_cancelled(self):
        if self.cancelled:
            raise ExecutionStopped('execution_interrupted')

    def register(self, callback):
        """Register a resource closer; invoke it immediately if already cancelled."""
        with self._lock:
            if self._event.is_set():
                callback_id = None
            else:
                callback_id = self._next_callback
                self._next_callback += 1
                self._callbacks[callback_id] = callback

        if callback_id is None:
            self._invoke(callback)
            return lambda: None

        def unregister():
            with self._lock:
                self._callbacks.pop(callback_id, None)

        return unregister

    def cancel(self):
        with self._lock:
            if self._event.is_set():
                return False
            self._event.set()
            callbacks = tuple(self._callbacks.values())
            self._callbacks.clear()

        for callback in callbacks:
            self._invoke(callback)
        return True

    @staticmethod
    def _invoke(callback):
        try:
            callback()
        except Exception:
            logging.getLogger(__name__).exception('Cancellation resource cleanup failed')
