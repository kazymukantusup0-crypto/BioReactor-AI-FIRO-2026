"""Isolated Ollama HTTP A/B harness for Qwen3 GPU layer placement.

This tool never changes BioReactor provider configuration. `preflight` is read-only.
`compare` runs A then B sequentially only when every cold-start gate passes.
"""
from __future__ import annotations

import argparse
import csv
import ctypes
import http.client
import io
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

import psutil

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from ollama_memory_snapshot import commit_snapshot, process_rows  # noqa: E402

ROOT = HERE.parent
MODEL = "qwen3:8b"
API = "http://127.0.0.1:11434"
COLD_START_GATE_MIB = 9373.6
RUNTIME_FLOOR_MIB = 6246.4
GPU_STOP_C = 82.0  # Existing project stop policy, not a universal hardware limit.
PREFLIGHT_COUNT = 3
PREFLIGHT_INTERVAL_S = 10.0
SAMPLE_INTERVAL_S = 1.0
QUESTION = "Что означает BMP и почему лабораторный BMP не равен фактическому выходу метана в реакторе?"
QUALITY_RUBRIC = [
    "completeness: defines BMP and distinguishes laboratory potential from reactor yield",
    "scientific correctness: separates measured, predicted, and conditional claims",
    "unsupported claims: flags numbers or facts not grounded in provided evidence",
    "clarity: answers the question directly without requiring missing batch data",
]
UNICODE_PROBE = "Русский; қазақша: ә ғ қ ң ө ұ ү һ і; CH₄; 37 °C; VS; 0.6 кг × 250 мл/г."
PROFILES: dict[str, dict[str, int]] = {
    "A": {"num_ctx": 4096, "num_batch": 32, "num_gpu": 16, "num_thread": 6},
    "B": {"num_ctx": 4096, "num_batch": 32, "num_gpu": -1, "num_thread": 6},
}


def now() -> str:
    return datetime.now().astimezone().isoformat()


def check_unicode() -> dict[str, Any]:
    for label, value in (("probe", UNICODE_PROBE), ("question", QUESTION)):
        raw = value.encode("utf-8", errors="strict")
        if raw.decode("utf-8", errors="strict").encode("utf-8") != raw:
            raise ValueError(f"INVALID_INPUT: UTF-8 byte round-trip failed for {label}")
        request_bytes = json.dumps({"prompt": value}, ensure_ascii=False).encode("utf-8")
        restored = json.loads(request_bytes.decode("utf-8", errors="strict"))["prompt"]
        if restored != value or restored.encode("utf-8") != raw:
            raise ValueError(f"INVALID_INPUT: JSON Unicode round-trip failed for {label}")
    return {
        "status": "PASS",
        "probe_utf8_sha256": sha256(UNICODE_PROBE.encode("utf-8")).hexdigest(),
        "question_utf8_sha256": sha256(QUESTION.encode("utf-8")).hexdigest(),
        "probe": UNICODE_PROBE,
        "question": QUESTION,
    }


def get_json(route: str, timeout: float = 4.0) -> dict[str, Any]:
    req = urllib.request.Request(API + route, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def gpu_snapshot() -> dict[str, Any]:
    query = ",".join((
        "name", "temperature.gpu", "utilization.gpu", "memory.used", "memory.total",
        "clocks_throttle_reasons.hw_thermal_slowdown",
        "clocks_throttle_reasons.sw_thermal_slowdown",
        "clocks_throttle_reasons.active",
    ))
    result = subprocess.run(
        ["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits"],
        check=True, capture_output=True, text=True, timeout=5,
    )
    rows = list(csv.reader(io.StringIO(result.stdout), skipinitialspace=True))
    if not rows or len(rows[0]) != 8:
        raise RuntimeError(f"GPU telemetry malformed: {result.stdout!r}")
    row = rows[0]
    return {
        "name": row[0], "temperature_c": float(row[1]),
        "utilization_pct": float(row[2]), "vram_used_mib": int(row[3]),
        "vram_total_mib": int(row[4]), "hw_thermal_slowdown": row[5],
        "sw_thermal_slowdown": row[6], "active_throttle_reasons": row[7],
    }


def sample(index: int) -> dict[str, Any]:
    row: dict[str, Any] = {"index": index, "timestamp_local": now()}
    try:
        vm = psutil.virtual_memory()
        row["free_ram_mib"] = round(vm.available / (1024 * 1024), 1)
    except Exception as exc:
        row["free_ram_error"] = f"{type(exc).__name__}: {exc}"
    try:
        row["commit"] = commit_snapshot()
    except Exception as exc:
        row["commit_error"] = f"{type(exc).__name__}: {exc}"
    try:
        row["gpu"] = gpu_snapshot()
    except Exception as exc:
        row["gpu_error"] = f"{type(exc).__name__}: {exc}"
    try:
        row["ollama_processes"] = process_rows()
    except Exception as exc:
        row["process_error"] = f"{type(exc).__name__}: {exc}"
    try:
        row["api_version"] = get_json("/api/version")
        row["running_models"] = get_json("/api/ps").get("models", [])
    except Exception as exc:  # Missing API telemetry must block the experiment.
        row["api_error"] = f"{type(exc).__name__}: {exc}"
    return row


def sample_safety_error(row: dict[str, Any], *, preflight: bool = False) -> str | None:
    if "telemetry_errors" in row:
        return "telemetry errors: " + "; ".join(row["telemetry_errors"])
    telemetry_errors = [k for k in ("free_ram_error", "commit_error", "gpu_error", "process_error") if k in row]
    if telemetry_errors:
        return "; ".join(f"{key}={row[key]}" for key in telemetry_errors)
    for key in ("free_ram_mib", "commit", "gpu", "api_version", "running_models"):
        if key not in row:
            return f"missing required telemetry: {key}"
    if preflight and row["free_ram_mib"] < COLD_START_GATE_MIB:
        return f"free RAM {row['free_ram_mib']} MiB below cold-start gate {COLD_START_GATE_MIB} MiB"
    if not preflight and row["free_ram_mib"] < RUNTIME_FLOOR_MIB:
        return f"free RAM {row['free_ram_mib']} MiB below runtime floor {RUNTIME_FLOOR_MIB} MiB"
    gpu = row["gpu"]
    if row.get("api_version", {}).get("version") != "0.40.15":
        return f"unexpected or unverified Ollama version: {row.get('api_version')}"
    if gpu["temperature_c"] >= GPU_STOP_C:
        return f"GPU reached existing stop threshold {GPU_STOP_C} C"
    if gpu["hw_thermal_slowdown"] != "Not Active" or gpu["sw_thermal_slowdown"] != "Not Active":
        return "GPU thermal slowdown is active"
    if "api_error" in row:
        return row["api_error"]
    if preflight and row.get("running_models"):
        return "Ollama already has a loaded model; refusing to disturb it"
    return None


def preflight() -> dict[str, Any]:
    trace = {
        "started_local": now(), "model": MODEL,
        "cold_start_gate_mib": COLD_START_GATE_MIB,
        "runtime_floor_mib": RUNTIME_FLOOR_MIB,
        "required_consecutive_samples": PREFLIGHT_COUNT,
        "interval_seconds": PREFLIGHT_INTERVAL_S,
        "samples": [],
    }
    reasons: list[str] = []
    for i in range(PREFLIGHT_COUNT):
        row = sample(i + 1)
        trace["samples"].append(row)
        error = sample_safety_error(row, preflight=True)
        if error:
            reasons.append(f"sample {i + 1}: {error}")
        if i + 1 < PREFLIGHT_COUNT:
            time.sleep(PREFLIGHT_INTERVAL_S)
    trace["finished_local"] = now()
    trace["status"] = "PASS" if not reasons else "BLOCKED"
    trace["blocking_reasons"] = reasons
    return trace


def log_snapshot() -> dict[str, dict[str, Any]]:
    logdir = Path(os.getenv("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "Ollama"
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(logdir.glob("*.log")):
        try:
            st = path.stat()
            result[str(path)] = {"size": st.st_size, "mtime": st.st_mtime}
        except OSError:
            continue
    return result


def write_log_delta(before: dict[str, dict[str, Any]], output: Path) -> None:
    after = log_snapshot()
    chunks = []
    for name in sorted(set(before) | set(after)):
        old_size = before.get(name, {}).get("size", 0)
        current = after.get(name)
        if current is None:
            continue
        try:
            data = Path(name).read_bytes()
            if current["size"] < old_size:  # Rotated/truncated: retain full new file.
                old_size = 0
            delta = data[old_size:].decode("utf-8", errors="replace")
            chunks.append(f"===== {name} offset={old_size} size={current['size']} =====\n{delta}")
        except OSError as exc:
            chunks.append(f"===== {name} read_error={exc} =====\n")
    output.write_text("\n".join(chunks), encoding="utf-8")


class StreamJob:
    """One request with a closable socket; closing it cancels this request only."""
    def __init__(self, body: dict[str, Any], path: str = "/api/chat"):
        self.body = body
        self.path = path
        self.conn = http.client.HTTPConnection("127.0.0.1", 11434, timeout=None)
        self.done = threading.Event()
        self.cancelled = False
        self.events: list[dict[str, Any]] = []
        self.text_parts: list[str] = []
        self.error: str | None = None
        self.status: int | None = None
        self.started = time.monotonic()
        self.cancel_requested_local: str | None = None
        self.http_closed_local: str | None = None
        self.response: http.client.HTTPResponse | None = None
        self.thread = threading.Thread(target=self._worker, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def _worker(self) -> None:
        try:
            raw = json.dumps(self.body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.conn.request("POST", self.path, body=raw, headers={"Content-Type": "application/json; charset=utf-8"})
            response = self.conn.getresponse()
            self.response = response
            self.status = response.status
            if response.status != 200:
                self.error = f"HTTP {response.status}: {response.read().decode('utf-8', errors='replace')}"
                return
            while True:
                line = response.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                event = json.loads(line.decode("utf-8"))
                self.events.append(event)
                content = event.get("message", {}).get("content")
                if isinstance(content, str):
                    self.text_parts.append(content)
                if event.get("done"):
                    break
        except Exception as exc:
            if not self.cancelled:
                self.error = f"{type(exc).__name__}: {exc}"
        finally:
            self.done.set()
            try:
                self.conn.close()
            except Exception:
                pass
            self.http_closed_local = now()

    def cancel(self) -> None:
        self.cancelled = True
        if self.cancel_requested_local is None:
            self.cancel_requested_local = now()
        if self.response is not None:
            try:
                self.response.close()
            except Exception:
                pass
        sock = getattr(self.conn, "sock", None)
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass
        self.conn.close()


def monitored_request(body: dict[str, Any], label: str, timeout_s: float = 180.0,
                      path: str = "/api/chat") -> dict[str, Any]:
    job = StreamJob(body, path=path)
    samples: list[dict[str, Any]] = []
    started = now()
    job.start()
    reason = None
    try:
        while not job.done.wait(SAMPLE_INTERVAL_S):
            try:
                row = sample(len(samples) + 1)
            except Exception as exc:
                reason = f"telemetry failure: {type(exc).__name__}: {exc}"
                job.cancel()
                break
            samples.append(row)
            reason = sample_safety_error(row, preflight=False)
            if time.monotonic() - job.started >= timeout_s:
                reason = f"request timeout after {timeout_s} seconds"
            if reason:
                job.cancel()
                break
    except KeyboardInterrupt:
        reason = "operator cancellation (Ctrl+C)"
        job.cancel()
    job.thread.join(timeout=5)
    if job.thread.is_alive():
        job.cancel()
        job.thread.join(timeout=5)
    try:
        final_sample = sample(len(samples) + 1)
    except Exception as exc:
        final_sample = {"timestamp_local": now(), "telemetry_error": f"{type(exc).__name__}: {exc}"}
    samples.append(final_sample)
    return {
        "label": label, "started_local": started, "finished_local": now(),
        "elapsed_seconds": round(time.monotonic() - job.started, 3),
        "http_status": job.status, "cancelled": job.cancelled,
        "cancel_requested_local": job.cancel_requested_local,
        "http_closed_local": job.http_closed_local,
        "worker_stopped": not job.thread.is_alive(),
        "safety_or_timeout_reason": reason, "error": job.error,
        "events": list(job.events), "text": "".join(job.text_parts),
        "telemetry": list(samples),
    }


def ollama_logs_to(outdir: Path, profile: str, before: dict[str, dict[str, Any]]) -> None:
    write_log_delta(before, outdir / f"profile_{profile}_ollama_log_delta.txt")


def unload_model() -> dict[str, Any]:
    body = {"model": MODEL, "prompt": "", "keep_alive": 0, "stream": False}
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(API + "/api/generate", data=raw, method="POST", headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                models = get_json("/api/ps").get("models", [])
                if not models:
                    return {"status": "UNLOADED", "response": payload, "models": models}
                time.sleep(1)
            return {"status": "UNLOAD_NOT_CONFIRMED", "response": payload, "models": get_json("/api/ps").get("models", [])}
    except Exception as exc:
        return {"status": "UNLOAD_ERROR", "error": f"{type(exc).__name__}: {exc}"}


def one_profile(name: str, outdir: Path, question: str) -> dict[str, Any]:
    cfg = {"profile": name, "model": MODEL, "options": PROFILES[name], "temperature": 0,
           "num_predict": 300, "keep_alive_during_run": "5m", "post_run_unload": True,
           "prompt": question, "prompt_utf8_sha256": sha256(question.encode("utf-8")).hexdigest()}
    path = outdir / f"profile_{name}_config.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    before_logs = log_snapshot()
    result: dict[str, Any] = {"config": cfg, "started_local": now()}
    if get_json("/api/ps").get("models", []):
        result.update(status="BLOCKED", reason="Ollama has a loaded model; refusing to unload or replace it")
        return result
    admission_sample = sample(0)
    admission_error = sample_safety_error(admission_sample, preflight=True)
    result["immediate_preload_sample"] = admission_sample
    if admission_error:
        result.update(status="BLOCKED", reason=f"preload gate changed after three-point preflight: {admission_error}")
        return result
    load_body = {"model": MODEL, "prompt": "", "stream": False, "keep_alive": "5m", "options": cfg["options"]}
    load = monitored_request(load_body, f"{name}_load", path="/api/generate")
    result["load"] = load
    models = get_json("/api/ps").get("models", [])
    result["api_ps_after_load"] = models
    if not load["worker_stopped"]:
        result["status"] = "CANCEL_UNCONFIRMED"
        result["post_failed_load_processes"] = process_rows()
        ollama_logs_to(outdir, name, before_logs)
        return result
    if load["cancelled"] or load["error"] or not models:
        result["status"] = "FAILED_OR_CANCELLED_LOAD"
        result["post_failed_load_processes"] = process_rows()
        result["unload"] = unload_model() if models else {"status": "NO_MODEL_REPORTED; no unload request sent to avoid triggering a new load"}
        ollama_logs_to(outdir, name, before_logs)
        return result
    prompt_body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": question}],
        "stream": True, "keep_alive": "5m",
        "options": {**cfg["options"], "temperature": 0, "num_predict": 300},
        "think": False,
    }
    result["generation"] = monitored_request(prompt_body, f"{name}_generation")
    if not result["generation"]["worker_stopped"]:
        result["status"] = "CANCEL_UNCONFIRMED"
        result["post_unconfirmed_cancel_processes"] = process_rows()
        ollama_logs_to(outdir, name, before_logs)
        return result
    result["api_ps_before_unload"] = get_json("/api/ps").get("models", [])
    result["unload"] = unload_model()
    result["post_unload_sample"] = sample(-1)
    if result["unload"].get("status") != "UNLOADED":
        result["status"] = "UNLOAD_NOT_CONFIRMED"
    elif result["generation"].get("cancelled") or result["generation"].get("error"):
        result["status"] = "GENERATION_INTERRUPTED_OR_FAILED"
    else:
        result["status"] = "COMPLETED_QUALITY_REVIEW_REQUIRED"
    ollama_logs_to(outdir, name, before_logs)
    return result


def run_compare(outdir: Path) -> dict[str, Any]:
    outdir.mkdir(parents=True, exist_ok=True)
    unicode = check_unicode()
    result: dict[str, Any] = {
        "created_local": now(), "model": MODEL, "unicode_roundtrip": unicode,
        "profiles": [], "quality_review": "NOT_ASSESSED; requires independent review of both identical-prompt answers",
        "quality_rubric": QUALITY_RUBRIC,
    }
    for name in ("A", "B"):
        pf = preflight()
        result[f"preflight_before_{name}"] = pf
        (outdir / f"preflight_before_{name}.json").write_text(json.dumps(pf, ensure_ascii=False, indent=2), encoding="utf-8")
        if pf["status"] != "PASS":
            result["status"] = "BLOCKED"
            result["blocked_before_profile"] = name
            break
        profile_result = one_profile(name, outdir, QUESTION)
        result["profiles"].append(profile_result)
        (outdir / f"profile_{name}_result.json").write_text(json.dumps(profile_result, ensure_ascii=False, indent=2), encoding="utf-8")
        if profile_result.get("status") != "COMPLETED_QUALITY_REVIEW_REQUIRED":
            result["status"] = profile_result.get("status", "FAILED")
            result["blocked_after_profile"] = name
            break
    else:
        result["status"] = "COMPLETED_QUALITY_REVIEW_REQUIRED"
    result["finished_local"] = now()
    (outdir / "comparison_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    pf = sub.add_parser("preflight", help="three read-only admission samples; no model load")
    pf.add_argument("--output", type=Path, required=True)
    compare = sub.add_parser("compare", help="guarded sequential A/B run; loads Qwen only after PASS")
    compare.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    check_unicode()
    if args.command == "preflight":
        result = preflight()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "PASS" else 2
    result = run_compare(args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "COMPLETED_QUALITY_REVIEW_REQUIRED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
