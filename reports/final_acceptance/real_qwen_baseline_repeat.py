"""One-off, sequential real-Qwen baseline against the running Dashboard API.

This is a QA harness, not application code. It records each API exchange,
job event, provider/tool trace, system telemetry sample, and independent rubric.
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

import psutil


ROOT = pathlib.Path(__file__).resolve().parents[2]
BASE = "http://127.0.0.1:8766"
OUT = ROOT / "reports" / "real_qwen_baseline_20261109_repeat"
OLLAMA_LOG = pathlib.Path.home() / "AppData" / "Local" / "Ollama" / "server.log"
MODEL = "qwen3:8b"
RAM_MIN_MIB = 6246.4  # prior successful run on this exact Q4_K_M configuration
POLL_SECONDS = 1.0
SAMPLE_SECONDS = 2.0
JOB_TIMEOUT_SECONDS = 220
ACTIVE_JOB_ID = None

SCENARIOS = [
    {
        "name": "01_bmp_vs_reactor",
        "turns": [
            "Чем лабораторный BMP отличается от фактического выхода метана в реакторе? Объясни, почему результат BMP нельзя напрямую считать измеренным выходом конкретной установки.",
        ],
        "rubric": {
            "must_explain_bmp_lab_potential": "BMP описан как лабораторный потенциал/испытание, не как измерение установки",
            "must_distinguish_operating_reactor": "названы факторы процесса/эксплуатации, влияющие на реальный выход",
            "must_not_invent_transfer_factor": "нет произвольного числового коэффициента пересчёта BMP в выход установки",
        },
    },
    {
        "name": "02_conditional_arithmetic",
        "turns": [
            "Условный арифметический пример: масса VS равна 0,6 кг, BMP задан как допущение 250 мл CH₄/г VS. Рассчитай потенциальный объём CH₄. Явно укажи, что это условный расчёт, а не измерение.",
        ],
        "rubric": {
            "correct_result": "0.15 м³ CH₄ (эквивалентно 150 л)",
            "correct_unit": "объём указан в м³ или литрах, не в массе",
            "conditional_not_measured": "результат назван условным потенциалом, не фактическим измерением",
        },
    },
    {
        "name": "03_new_batch_and_correction",
        "turns": [
            "Начинаем новую партию: 5 кг пищевых отходов, реактор номинальной вместимостью 90 л. Дай предварительную оценку потенциального метана по применимому научному профилю, если он доступен. Отдели литературный/условный расчёт от измерения и не считай номинальную вместимость рабочим объёмом.",
            "Исправление для этой же партии: фактическая масса 6 кг, а не 5 кг. Пересчитай оценку, сохранив пищевые отходы и реактор номинальной вместимостью 90 л.",
        ],
        "rubric": {
            "same_batch": "исправление применено к той же партии, без смешения партий",
            "corrected_mass": "после исправления используется 6 кг, а не 5 кг",
            "reactor_preserved": "сохранены 90 л номинальной ёмкости; она не названа массой сырья или рабочим объёмом",
            "scientific_provenance": "потенциал/литературный расчёт отделён от измеренного результата",
        },
    },
]


def now():
    return datetime.now(timezone.utc).isoformat()


def request(method: str, path: str, payload=None, timeout=20):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
            return {"status_code": response.status, "body": json.loads(raw.decode("utf-8")),
                    "elapsed_seconds": round(time.monotonic() - started, 4), "at_utc": now()}
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            body = raw.decode("utf-8", errors="replace")
        return {"status_code": exc.code, "body": body,
                "elapsed_seconds": round(time.monotonic() - started, 4), "at_utc": now()}


def gpu_sample():
    query = "name,temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw,pstate"
    raw = subprocess.check_output(["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits"],
                                  timeout=5, text=True).strip().splitlines()[0]
    cells = [v.strip() for v in raw.split(",")]
    details = subprocess.check_output(["nvidia-smi", "-q", "-d", "TEMPERATURE,PERFORMANCE"],
                                      timeout=5, text=True)
    target = re.search(r"^\s*GPU Target Temperature\s*:\s*(\d+)\s*C\s*$", details, re.M)
    hw = re.search(r"^\s*HW Thermal Slowdown\s*:\s*(Active|Not Active)\s*$", details, re.M)
    sw = re.search(r"^\s*SW Thermal Slowdown\s*:\s*(Active|Not Active)\s*$", details, re.M)
    if len(cells) != 7 or target is None or hw is None:
        raise RuntimeError("Incomplete nvidia-smi telemetry")
    return {
        "name": cells[0], "temperature_c": float(cells[1]), "utilization_pct": float(cells[2]),
        "vram_used_mib": float(cells[3]), "vram_total_mib": float(cells[4]),
        "power_w": float(cells[5]), "pstate_diagnostic": cells[6],
        "device_target_c": int(target.group(1)),
        "hw_thermal_slowdown": hw.group(1) == "Active",
        "sw_thermal_slowdown": sw.group(1) == "Active",
    }


def commit_headroom_mib():
    # Query native Windows performance counters; no system configuration changes.
    command = r"$x=Get-Counter '\Memory\Commit Limit','\Memory\Committed Bytes'; $h=@{}; foreach($s in $x.CounterSamples){$h[$s.Path.Split('\')[-1]]=$s.CookedValue}; [math]::Round(($h['Commit Limit']-$h['Committed Bytes'])/1MB,1)"
    result = subprocess.check_output(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                                     timeout=8, text=True, stderr=subprocess.STDOUT).strip()
    return float(result.splitlines()[-1])


def ollama_ps():
    response = request("GET", "http://127.0.0.1:11434/api/ps") if False else None
    req = urllib.request.Request("http://127.0.0.1:11434/api/ps")
    with urllib.request.urlopen(req, timeout=3) as r:
        return json.loads(r.read().decode("utf-8"))


def runner_processes():
    found = []
    for proc in psutil.process_iter(["pid", "name", "memory_info", "cpu_times", "create_time"]):
        try:
            name = proc.info.get("name") or ""
            if name.lower().startswith("ollama"):
                memory = proc.info.get("memory_info")
                found.append({"pid": proc.info["pid"], "name": name,
                              "rss_mib": round(memory.rss / 1048576, 1) if memory else None,
                              "cpu_seconds": round(sum(proc.info["cpu_times"][:2]), 2) if proc.info.get("cpu_times") else None,
                              "created_epoch": proc.info.get("create_time")})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return found


def telemetry():
    vm = psutil.virtual_memory()
    gpu = gpu_sample()
    ps = ollama_ps()
    return {
        "at_utc": now(), "free_ram_mib": round(vm.available / 1048576, 1),
        "ram_total_mib": round(vm.total / 1048576, 1),
        "commit_headroom_mib": commit_headroom_mib(),
        "gpu": gpu, "ollama_api_ps": ps, "ollama_processes": runner_processes(),
    }


def safety_reasons(sample, new_log_text):
    reasons = []
    if sample["free_ram_mib"] < RAM_MIN_MIB:
        reasons.append("free_physical_ram_below_prior_successful_run_threshold")
    gpu = sample["gpu"]
    if gpu["temperature_c"] >= gpu["device_target_c"]:
        reasons.append("gpu_at_or_above_device_target")
    if gpu["hw_thermal_slowdown"]:
        reasons.append("gpu_hardware_thermal_slowdown_active")
    if re.search(r"CUDA error|0xc0000409|CUDA runner.{0,50}(?:exited|crash)|runner process has terminated",
                 new_log_text, re.I | re.S):
        reasons.append("new_ollama_cuda_or_runner_failure_in_log")
    return reasons


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def provider_evidence(reply):
    statuses = reply.get("provider_status") or []
    metadata = reply.get("technical_metadata") or {}
    direct = [s for s in statuses if isinstance(s, dict) and s.get("model") == MODEL]
    metrics = metadata.get("provider_generation_metrics") or []
    actual = any(s.get("actual_generation") is True for s in direct)
    actual = actual or any(isinstance(m, dict) and m.get("status") == "ok" for m in metrics)
    return {"provider_status_rows": direct, "provider_generation_metrics": metrics,
            "actual_qwen_generation_claimed_by_backend": actual,
            "tool_calls": reply.get("tools"), "technical_metadata": metadata}


def flattened_text(reply):
    vals = [reply.get("answer"), reply.get("user_facing_answer")]
    return "\n".join(v if isinstance(v, str) else json.dumps(v, ensure_ascii=False) for v in vals if v is not None).lower()


def evaluate(scenario, turns):
    text = "\n".join(flattened_text(t.get("result", {}).get("reply") or {}) for t in turns)
    checks = {}
    if scenario["name"] == "01_bmp_vs_reactor":
        checks["must_explain_bmp_lab_potential"] = (
            bool(re.search(r"\bBMP\b|биохимическ.{0,30}метан", text, re.I))
            and bool(re.search(r"лабораторн|batch assay|batch test", text, re.I))
            and bool(re.search(r"потенциал|испытан|тест|определя", text, re.I))
        )
        checks["must_distinguish_operating_reactor"] = bool(re.search(r"реактор|установк|температур|времени удерж|нагрузк|перемеш|ингибир|эксплуатац", text, re.I))
        checks["must_not_invent_transfer_factor"] = not bool(re.search(r"(?:коэффициент|пересч[её]т|conversion factor).{0,50}\b\d+(?:[.,]\d+)?\s*%", text, re.I))
    elif scenario["name"] == "02_conditional_arithmetic":
        checks["correct_result"] = bool(re.search(r"(?:0[.,]15\s*(?:м\s*3|м³)|150\s*(?:л|литр))", text, re.I))
        checks["correct_unit"] = bool(re.search(r"(?:м\s*3|м³|\bл\b|литр)", text, re.I))
        checks["conditional_not_measured"] = bool(re.search(r"условн|допущен|потенциал", text, re.I)) and not bool(re.search(r"измеренн(?:ый|ое) результат|фактически измер", text, re.I))
    else:
        final = flattened_text(turns[-1].get("result", {}).get("reply") or {})
        checks["same_batch"] = bool(re.search(r"исправлен|замен|этой же партии|та же партия", final, re.I))
        checks["corrected_mass"] = bool(re.search(r"\b6\s*кг\b", final, re.I)) and not bool(re.search(r"\b5\s*кг\b", final, re.I))
        checks["reactor_preserved"] = bool(re.search(r"\b90\s*л\b", final, re.I))
        checks["scientific_provenance"] = bool(re.search(r"литератур|условн|потенциал|не измер|не является измер", final, re.I))
    return {"method": "independent rubric checks over actual API response; no model self-grading",
            "checks": checks, "passed": all(checks.values()), "response_text_used": text}


def run():
    global ACTIVE_JOB_ID
    OUT.mkdir(parents=True, exist_ok=True)
    log_offset = OLLAMA_LOG.stat().st_size if OLLAMA_LOG.exists() else None
    manifest = {
        "started_utc": now(), "dashboard_base": BASE, "api_route": "async Dashboard chat session/jobs (Runtime 9 for conversation_version=7)",
        "provider_expected": "offline loopback Ollama, strict Qwen3 8B", "model_expected": MODEL,
        "threshold_basis": {"free_ram_min_mib": RAM_MIN_MIB, "gpu": "below device-reported target; hardware thermal slowdown inactive", "pstate": "diagnostic only"},
        "ollama_log": str(OLLAMA_LOG), "ollama_log_offset_bytes_before_run": log_offset,
        "scenarios": [], "status": "RUNNING",
    }
    save(OUT / "manifest.json", manifest)
    health = request("GET", "/health")
    runtime = request("GET", "/api/dashboard/runtime")
    manifest["initial_health"] = health
    manifest["initial_runtime"] = runtime
    if health["status_code"] != 200 or runtime["status_code"] != 200 or not runtime["body"].get("worker_alive"):
        manifest.update(status="BLOCKED", block_reason="Dashboard health/runtime unavailable")
        save(OUT / "manifest.json", manifest)
        return 2
    active = {k: v for k, v in runtime["body"].get("counts", {}).items() if k in {"RUNNING", "QUEUED"} and v}
    if active:
        manifest.update(status="BLOCKED", block_reason="Other active/queued Dashboard jobs present", active_jobs=active)
        save(OUT / "manifest.json", manifest)
        return 2

    for scenario in SCENARIOS:
        print(f"SCENARIO_START {scenario['name']} {now()}", flush=True)
        entry = {"name": scenario["name"], "rubric_definition": scenario["rubric"], "turns": [], "status": "RUNNING"}
        manifest["scenarios"].append(entry)
        session_result = request("POST", "/api/dashboard/chat/sessions", {
            "mode": "offline", "context": {}, "conversation_version": "7"})
        entry["session_create"] = session_result
        if session_result["status_code"] != 201:
            entry.update(status="FAILED", failure="session creation failed")
            save(OUT / (scenario["name"] + ".json"), entry)
            manifest["status"] = "STOPPED"
            save(OUT / "manifest.json", manifest)
            return 1
        sid = session_result["body"]["id"]
        scenario_path = OUT / (scenario["name"] + ".json")
        save(scenario_path, entry)

        for turn_index, prompt in enumerate(scenario["turns"], start=1):
            turn = {"turn": turn_index, "prompt": prompt, "started_utc": now(), "api_calls": [], "telemetry": [],
                    "ollama_log_new_lines": [], "safety_events": []}
            entry["turns"].append(turn)
            pre = telemetry()
            turn["telemetry"].append({"phase": "immediately_before_request", **pre})
            reasons = safety_reasons(pre, "")
            if reasons:
                turn["safety_events"].append({"at_utc": now(), "reasons": reasons})
                turn["status"] = "BLOCKED"
                entry.update(status="BLOCKED", failure="resource/telemetry gate before request")
                save(scenario_path, entry)
                manifest.update(status="STOPPED", stop_reason=entry["failure"])
                save(OUT / "manifest.json", manifest)
                return 2
            snapshot = request("GET", f"/api/dashboard/chat/sessions/{sid}")
            turn["api_calls"].append({"operation": "get_session_before_turn", **snapshot})
            if snapshot["status_code"] != 200:
                turn["status"] = "FAILED"
                entry.update(status="FAILED", failure="session snapshot failed")
                save(scenario_path, entry)
                manifest.update(status="STOPPED", stop_reason=entry["failure"])
                save(OUT / "manifest.json", manifest)
                return 1
            request_id = uuid.uuid4().hex
            submit = request("POST", f"/api/dashboard/chat/sessions/{sid}/jobs", {
                "message": prompt, "request_id": request_id,
                "expected_state_version": snapshot["body"]["state_version"]})
            turn["request_id"] = request_id
            turn["api_calls"].append({"operation": "submit_job", **submit})
            if submit["status_code"] != 202:
                turn["status"] = "FAILED"
                entry.update(status="FAILED", failure="job submission rejected")
                save(scenario_path, entry)
                manifest.update(status="STOPPED", stop_reason=entry["failure"])
                save(OUT / "manifest.json", manifest)
                return 1
            job_id = submit["body"]["id"]
            ACTIVE_JOB_ID = job_id
            print(f"JOB_SUBMITTED {scenario['name']} turn={turn_index} job={job_id} {now()}", flush=True)
            turn["job_id"] = job_id
            turn["job_started_monotonic"] = time.monotonic()
            deadline = time.monotonic() + JOB_TIMEOUT_SECONDS
            next_sample = 0.0
            next_events = 0.0
            terminal = None
            last_log_offset = log_offset
            while time.monotonic() < deadline:
                if time.monotonic() >= next_sample:
                    try:
                        sample = telemetry()
                        new_log = ""
                        if OLLAMA_LOG.exists() and last_log_offset is not None:
                            with OLLAMA_LOG.open("rb") as log:
                                log.seek(last_log_offset)
                                raw = log.read()
                                last_log_offset = log.tell()
                            new_log = raw.decode("utf-8", errors="replace")
                            if new_log:
                                turn["ollama_log_new_lines"].append({"observed_at_utc": now(), "text": new_log})
                        sample["safety_reasons"] = safety_reasons(sample, new_log)
                        turn["telemetry"].append(sample)
                        print(json.dumps({"telemetry": scenario["name"], "turn": turn_index,
                                          "free_ram_mib": sample["free_ram_mib"],
                                          "commit_headroom_mib": sample["commit_headroom_mib"],
                                          "gpu": sample["gpu"], "safety_reasons": sample["safety_reasons"]},
                                         ensure_ascii=False), flush=True)
                        if sample["safety_reasons"]:
                            turn["safety_events"].append({"at_utc": now(), "reasons": sample["safety_reasons"], "sample": sample})
                            request("POST", f"/api/dashboard/jobs/{job_id}/cancel", {}, timeout=10)
                            turn["cancel_sent_for_safety"] = True
                            turn["status"] = "BLOCKED"
                            entry.update(status="BLOCKED", failure="resource/instability guard; current job cancelled")
                            save(scenario_path, entry)
                            manifest.update(status="STOPPED", stop_reason=entry["failure"])
                            save(OUT / "manifest.json", manifest)
                            return 2
                    except Exception as exc:
                        turn["safety_events"].append({"at_utc": now(), "reasons": ["telemetry_error"],
                                                       "error": f"{type(exc).__name__}: {exc}"})
                        request("POST", f"/api/dashboard/jobs/{job_id}/cancel", {}, timeout=10)
                        turn["cancel_sent_for_safety"] = True
                        turn["status"] = "BLOCKED"
                        entry.update(status="BLOCKED", failure="telemetry lost during inference; current job cancelled")
                        save(scenario_path, entry)
                        manifest.update(status="STOPPED", stop_reason=entry["failure"])
                        save(OUT / "manifest.json", manifest)
                        return 2
                    next_sample = time.monotonic() + SAMPLE_SECONDS

                status = request("GET", f"/api/dashboard/jobs/{job_id}")
                turn["api_calls"].append({"operation": "poll_job", **status})
                if status["status_code"] != 200:
                    turn["status"] = "FAILED"
                    entry.update(status="FAILED", failure="job status endpoint failed")
                    save(scenario_path, entry)
                    manifest.update(status="STOPPED", stop_reason=entry["failure"])
                    save(OUT / "manifest.json", manifest)
                    return 1
                terminal = status["body"]
                if time.monotonic() >= next_events:
                    ev = request("GET", f"/api/dashboard/jobs/{job_id}/events")
                    turn["api_calls"].append({"operation": "get_job_events", **ev})
                    next_events = time.monotonic() + 3.0
                save(scenario_path, entry)
                if terminal.get("terminal"):
                    break
                time.sleep(POLL_SECONDS)
            if not terminal or not terminal.get("terminal"):
                request("POST", f"/api/dashboard/jobs/{job_id}/cancel", {}, timeout=10)
                turn.update(status="TIMED_OUT", finished_utc=now())
                entry.update(status="STOPPED", failure="bounded job timeout; current job cancellation requested")
                save(scenario_path, entry)
                manifest.update(status="STOPPED", stop_reason=entry["failure"])
                save(OUT / "manifest.json", manifest)
                return 2

            turn["terminal_job"] = terminal
            ACTIVE_JOB_ID = None
            result = request("GET", f"/api/dashboard/jobs/{job_id}/result", timeout=30)
            turn["api_calls"].append({"operation": "get_job_result", **result})
            turn["result"] = result["body"]
            turn["elapsed_seconds"] = round(time.monotonic() - turn["job_started_monotonic"], 3)
            turn["finished_utc"] = now()
            reply = result["body"].get("reply") or {}
            turn["qwen_evidence"] = provider_evidence(reply)
            turn["session_after"] = request("GET", f"/api/dashboard/chat/sessions/{sid}")
            turn["scientific_state_after"] = request("GET", f"/api/dashboard/chat/sessions/{sid}/scientific-state")
            turn["api_calls"].append({"operation": "get_scientific_state", **turn["scientific_state_after"]})
            turn["independent_rubric_observation"] = "PENDING_MANUAL_REVIEW"
            entry["rubric_partial"] = evaluate(scenario, entry["turns"])
            entry["status"] = "COMPLETED" if terminal.get("status") == "COMPLETED" else "FAILED"
            if terminal.get("status") != "COMPLETED":
                entry["failure"] = "job did not complete successfully"
            save(scenario_path, entry)
            save(OUT / "manifest.json", manifest)
            if terminal.get("status") != "COMPLETED":
                manifest.update(status="STOPPED", stop_reason=entry.get("failure"))
                save(OUT / "manifest.json", manifest)
                return 1
            if not turn["qwen_evidence"]["actual_qwen_generation_claimed_by_backend"]:
                entry.update(status="FAILED", failure="backend trace does not confirm actual Qwen generation")
                save(scenario_path, entry)
                manifest.update(status="STOPPED", stop_reason=entry["failure"])
                save(OUT / "manifest.json", manifest)
                return 1

        entry["independent_rubric"] = evaluate(scenario, entry["turns"])
        entry["status"] = "COMPLETED"
        print(json.dumps({"SCENARIO_COMPLETE": scenario["name"], "seconds": [t.get("elapsed_seconds") for t in entry["turns"]],
                          "rubric": entry["independent_rubric"]["checks"],
                          "qwen_confirmed": [t.get("qwen_evidence", {}).get("actual_qwen_generation_claimed_by_backend") for t in entry["turns"]]},
                         ensure_ascii=False), flush=True)
        save(scenario_path, entry)
        save(OUT / "manifest.json", manifest)

    manifest.update(status="COMPLETED", finished_utc=now())
    save(OUT / "manifest.json", manifest)
    return 0


if __name__ == "__main__":
    try:
        rc = run()
        print(json.dumps({"exit_code": rc, "manifest": str(OUT / "manifest.json")}, ensure_ascii=False))
        raise SystemExit(rc)
    except Exception as exc:
        if ACTIVE_JOB_ID:
            try:
                request("POST", f"/api/dashboard/jobs/{ACTIVE_JOB_ID}/cancel", {}, timeout=10)
            except Exception:
                pass
        OUT.mkdir(parents=True, exist_ok=True)
        path = OUT / "runner_exception.json"
        save(path, {"at_utc": now(), "type": type(exc).__name__, "message": str(exc), "status": "FAILED_OR_BLOCKED"})
        print(json.dumps({"runner_exception": type(exc).__name__, "message": str(exc), "artifact": str(path)}, ensure_ascii=False), file=sys.stderr)
        raise
