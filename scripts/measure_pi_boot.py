"""Power-on test of the Pi in mode «always hotspot»: how long from power-on to the first data on the dashboard.

    .venv\\Scripts\\python scripts/measure_pi_boot.py --minutes 30      (runs alone; the laptop has no internet meanwhile)

1. waits until the Pi is gone (power off): no answer at 10.42.0.1 and 192.168.50.2
2. then, every second (laptop clock): which Wi-Fi the laptop is on, does the Pi answer at 10.42.0.1,
   does the dashboard (http://127.0.0.1:8766) show live data «через Wi-Fi Pi» with a real Arduino
3. at the first data: asks the Pi over 10.42.0.1 for its uptime and its own log times (seconds since the kernel
   started: BioReactor-Pi up, bridge started, Arduino boot line) — the Pi has no battery clock, so only uptime is exact
Power-on ≈ moment of the first data − Pi uptime − ~3 s (bootloader before the kernel; Pi 5).
Result: reports/pi_wifi/boot.log and boot.json.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/pi_wifi"
KEY = Path.home() / ".ssh/id_ed25519_bioreactor"
BOOTLOADER_S = 3.0


def log(text: str) -> None:
    line = f"{datetime.now():%H:%M:%S} {text}"
    print(line, flush=True)
    with open(OUT / "boot.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def get(url: str, timeout: float = 2) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return None


def run(cmd: list[str], timeout: float = 15) -> str:
    try:
        done = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return (done.stdout + done.stderr).decode("utf-8", errors="replace").strip()
    except Exception as error:
        return f"{type(error).__name__}: {error}"


def wifi() -> str:
    for line in run(["netsh", "wlan", "show", "interfaces"]).splitlines():
        if line.strip().startswith("SSID") and "BSSID" not in line:
            return line.split(":", 1)[1].strip()
    return "-"


def pi_up() -> bool:
    return any(get(f"http://{host}:8780/health", 1.5) for host in ("10.42.0.1", "192.168.50.2"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--minutes", type=float, default=30)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    end = time.time() + args.minutes * 60
    log("===== start: switch the Pi OFF (I wait until it is gone)")
    while pi_up():
        if time.time() > end:
            log("TIMEOUT: the Pi never went off")
            return 1
        time.sleep(1)
    off = time.time()
    log("Pi is OFF. Now switch it ON.")
    marks: dict[str, float] = {}
    last_wifi = None
    while time.time() < end:
        now = time.time()
        name = wifi()
        if name != last_wifi:
            log(f"laptop Wi-Fi: {name}")
            last_wifi = name
            if name == "BioReactor-Pi" and "laptop_joined" not in marks:
                marks["laptop_joined"] = now
        if "pi_health" not in marks and get("http://10.42.0.1:8780/health", 1.5):
            marks["pi_health"] = now
            log("Pi answers /health at 10.42.0.1")
        status = get("http://127.0.0.1:8766/api/reactor/status", 3) or {}
        source, link = status.get("source") or {}, status.get("link") or {}
        if link.get("ok") and source.get("route") == "pi_wifi" and source.get("arduino_port") not in (None, "virtual"):
            marks["dashboard_data"] = now
            readings = {k: v.get("value") for k, v in (status.get("readings") or {}).items()}
            log(f"FIRST DATA on the dashboard via Wi-Fi Pi: {readings}")
            pi = run(["ssh", "-i", str(KEY), "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=accept-new",
                      "bio@10.42.0.1",
                      "cat /proc/uptime; journalctl -b -o short-monotonic --no-pager -u NetworkManager -u bioreactor-pi "
                      "| grep -E 'Started Wi-Fi Hotspot|BioReactor Pi bridge on' | head -3; "
                      "journalctl -b -o short-monotonic --no-pager -u bioreactor-pi | grep -m1 -E 'Started bioreactor-pi'"])
            uptime = float(pi.split()[0]) if pi and pi.split()[0].replace(".", "", 1).isdigit() else None
            fetched = time.time()
            result = {"power_off_seen": datetime.fromtimestamp(off).isoformat(timespec="seconds"), "pi_log": pi}
            if uptime is not None:
                power_on = fetched - uptime - BOOTLOADER_S
                result["power_on_estimate"] = datetime.fromtimestamp(power_on).isoformat(timespec="seconds")
                result["seconds_from_power_on"] = {k: round(v - power_on, 1) for k, v in marks.items()}
                log(f"Pi uptime {uptime:.1f} s -> power-on ≈ {result['power_on_estimate']}")
                log(f"seconds from power-on: {result['seconds_from_power_on']}")
            log(f"Pi log (seconds since the kernel started):\n{pi}")
            (OUT / "boot.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
            return 0
        time.sleep(max(0.0, 1 - (time.time() - now)))
    log("TIMEOUT: no data on the dashboard via Wi-Fi Pi")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
