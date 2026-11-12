"""Passive Ollama process and host-memory sampler for Windows; never loads a model."""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes
import json
import psutil
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

MIB = 1024 * 1024


class PERFORMANCE_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.wintypes.DWORD),
        ("CommitTotal", ctypes.c_size_t),
        ("CommitLimit", ctypes.c_size_t),
        ("CommitPeak", ctypes.c_size_t),
        ("PhysicalTotal", ctypes.c_size_t),
        ("PhysicalAvailable", ctypes.c_size_t),
        ("SystemCache", ctypes.c_size_t),
        ("KernelTotal", ctypes.c_size_t),
        ("KernelPaged", ctypes.c_size_t),
        ("KernelNonpaged", ctypes.c_size_t),
        ("PageSize", ctypes.c_size_t),
        ("HandleCount", ctypes.wintypes.DWORD),
        ("ProcessCount", ctypes.wintypes.DWORD),
        ("ThreadCount", ctypes.wintypes.DWORD),
    ]


def commit_snapshot() -> dict[str, float]:
    info = PERFORMANCE_INFORMATION()
    info.cb = ctypes.sizeof(info)
    ok = ctypes.WinDLL("psapi.dll").GetPerformanceInfo(
        ctypes.byref(info), ctypes.sizeof(info)
    )
    if not ok:
        raise OSError(ctypes.get_last_error(), "GetPerformanceInfo failed")
    total = info.CommitTotal * info.PageSize
    limit = info.CommitLimit * info.PageSize
    return {
        "commit_total_mib": round(total / MIB, 1),
        "commit_limit_mib": round(limit / MIB, 1),
        "commit_headroom_mib": round((limit - total) / MIB, 1),
        "physical_available_mib": round(info.PhysicalAvailable * info.PageSize / MIB, 1),
    }


def api_get(base: str, route: str) -> dict[str, Any]:
    request = urllib.request.Request(base.rstrip("/") + route, method="GET")
    with urllib.request.urlopen(request, timeout=3) as response:
        return {"http_status": response.status, "body": json.load(response)}


def process_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    wanted = {"ollama app.exe", "ollama app", "ollama.exe", "ollama", "llama-server.exe", "llama-server"}
    for proc in psutil.process_iter():
        try:
            name = proc.name()
            if name.casefold() not in wanted:
                continue
            info = proc.as_dict(attrs=["pid", "name", "exe", "cmdline", "ppid", "create_time", "num_threads"])
            parent = psutil.Process(info["ppid"]) if info.get("ppid") else None
            memory = proc.memory_full_info()
            rows.append({
                "pid": info["pid"], "name": name, "exe": info.get("exe"),
                "cmdline": info.get("cmdline"), "ppid": info.get("ppid"),
                "parent_name": parent.name() if parent else None,
                "parent_exe": parent.exe() if parent else None,
                "created_local": datetime.fromtimestamp(info["create_time"]).astimezone().isoformat(),
                "threads": proc.num_threads(), "handles": proc.num_handles(),
                "working_set_mib": round(memory.rss / MIB, 1),
                "private_working_set_mib": round(memory.uss / MIB, 1),
                "private_bytes_mib": round(memory.private / MIB, 1),
                "virtual_bytes_mib": round(memory.vms / MIB, 1),
                "peak_working_set_mib": round(memory.peak_wset / MIB, 1),
                "peak_private_bytes_mib": round(memory.peak_pagefile / MIB, 1),
            })
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess) as exc:
            rows.append({"pid": getattr(proc, "pid", None), "error": type(exc).__name__})
    return rows


def take_sample(index: int, ollama_url: str) -> dict[str, Any]:
    now = datetime.now().astimezone().isoformat()
    vm = psutil.virtual_memory()
    sample: dict[str, Any] = {
        "sample": index,
        "timestamp_local": now,
        "available_physical_ram_mib_psutil": round(vm.available / MIB, 1),
        "memory_percent": vm.percent,
        "commit": commit_snapshot(),
        "processes": process_rows(),
    }
    try:
        sample["ollama_version_api"] = api_get(ollama_url, "/api/version")
        sample["ollama_running_models"] = api_get(ollama_url, "/api/ps")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        sample["ollama_api_error"] = f"{type(exc).__name__}: {exc}"
    return sample


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=6)
    parser.add_argument("--interval-seconds", type=float, default=10)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    args = parser.parse_args()
    if args.samples < 2 or args.interval_seconds < 1:
        parser.error("use at least 2 samples and an interval of at least 1 second")
    trace = {"started_local": datetime.now().astimezone().isoformat(), "samples": []}
    for i in range(args.samples):
        trace["samples"].append(take_sample(i + 1, args.ollama_url))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
        if i + 1 < args.samples:
            time.sleep(args.interval_seconds)
    trace["finished_local"] = datetime.now().astimezone().isoformat()
    args.output.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = []
    for sample in trace["samples"]:
        app = next((p for p in sample["processes"] if p.get("name", "").casefold() == "ollama app.exe"), {})
        summary.append({
            "at": sample["timestamp_local"],
            "free_mib": sample["available_physical_ram_mib_psutil"],
            "commit_headroom_mib": sample["commit"]["commit_headroom_mib"],
            "ollama_app": {k: app.get(k) for k in ("pid", "working_set_mib", "private_working_set_mib", "private_bytes_mib", "threads", "handles")},
            "api": sample.get("ollama_version_api", {}).get("http_status"),
            "loaded_models": sample.get("ollama_running_models", {}).get("body", {}).get("models"),
        })
    print(json.dumps({"output": str(args.output), "samples": summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
