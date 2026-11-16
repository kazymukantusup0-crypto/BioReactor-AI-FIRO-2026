"""Record GPU / Ollama / power state once per second while something slow runs.

Usage (in a second terminal, or in the background):
    .venv\\Scripts\\python scripts\\monitor_gpu.py --output docs/gpu_trace.csv --seconds 600

Each row: time, `ollama ps` (share of the model on the GPU), nvidia-smi (temperature,
SM clock, memory used, power draw / limit, P-state, utilization, active clock-event
reasons such as thermal or power cap), and whether the laptop runs on battery.
Only the standard library and the nvidia-smi / Ollama that are already installed are used.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import time
import urllib.request
from pathlib import Path

QUERY = ("temperature.gpu,clocks.sm,clocks.mem,memory.used,power.draw,power.limit,pstate,utilization.gpu,"
         "clocks_event_reasons.active,clocks_event_reasons.sw_power_cap,clocks_event_reasons.hw_slowdown,"
         "clocks_event_reasons.hw_thermal_slowdown,clocks_event_reasons.sw_thermal_slowdown,"
         "clocks_event_reasons.hw_power_brake_slowdown")
NAMES = ["temp_c", "sm_mhz", "mem_mhz", "vram_used_mib", "power_w", "power_limit_w", "pstate", "util_pct",
         "reasons_mask", "sw_power_cap", "hw_slowdown", "hw_thermal", "sw_thermal", "power_brake"]


def nvidia() -> dict:
    try:
        out = subprocess.run(["nvidia-smi", f"--query-gpu={QUERY}", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=5, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return {}
    return dict(zip(NAMES, [part.strip() for part in out.split(",")]))


def ollama_ps(url: str) -> dict:
    try:
        with urllib.request.urlopen(f"{url}/api/ps", timeout=2) as response:
            models = json.loads(response.read().decode("utf-8")).get("models", [])
    except (OSError, ValueError):
        return {"ollama": "down"}
    if not models:
        return {"ollama": "no model"}
    parts = []
    for model in models:
        size, vram = model.get("size") or 0, model.get("size_vram") or 0
        parts.append(f"{model.get('name')} {round(100 * vram / size) if size else 0}% GPU "
                     f"{vram / 2**30:.2f}/{size / 2**30:.2f} GiB ctx {model.get('context_length')}")
    return {"ollama": " | ".join(parts)}


def on_battery() -> str:
    """'AC' or 'battery' (Win32_Battery.BatteryStatus 2 = on mains), '?' when unknown."""
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "(Get-CimInstance Win32_Battery).BatteryStatus"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "?"
    return {"2": "AC", "1": "battery"}.get(out, out or "no battery")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=600)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--ollama", default="http://127.0.0.1:11434")
    args = parser.parse_args()
    power = on_battery()
    started = time.time()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["t_s", "power_source", *NAMES, "ollama"])
        writer.writeheader()
        while time.time() - started < args.seconds:
            row = {"t_s": round(time.time() - started, 1), "power_source": power, **nvidia(), **ollama_ps(args.ollama)}
            writer.writerow(row)
            handle.flush()
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
