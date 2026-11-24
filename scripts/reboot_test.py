"""Test 5 without a person: reboot the Pi and time «power-on -> first data via the Pi's Wi-Fi», then give the laptop
its internet back. Run on the laptop (school Wi-Fi + cable connected):

    .venv\\Scripts\\python scripts/reboot_test.py

1. the school Wi-Fi profile is set to «connect manually» for the test (otherwise Windows would jump to it while the
   Pi is rebooting), the laptop joins BioReactor-Pi
2. the dashboard's own client (src/hardware/client.py, mode auto) runs here with the Pi's Wi-Fi and bioreactor.local
   as candidates — the cable address is left out, as if the cable were unplugged (the cable stays as MY way to the Pi)
3. «sudo systemctl reboot» over the cable; then every 0.5 s: laptop Wi-Fi, /health at 10.42.0.1, client data
4. at the first data via Wi-Fi Pi with the real Arduino: the Pi's uptime and log times (over the cable)
5. ALWAYS at the end (finally): school Wi-Fi back to «connect automatically» and connected again
Result: reports/pi_wifi/reboot.log + reboot.json. Time from the kernel start is exact (uptime); add ~4 s of
bootloader for «from power-on» (Pi 5 EEPROM bootloader).
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.hardware.client import ReactorClient  # noqa: E402

OUT = ROOT / "reports/pi_wifi"
SCHOOL = "219wifi-5GHZ"
PI_WIFI = "BioReactor-Pi"
BOOTLOADER_S = 4.0
MAX_S = 480


def log(text: str) -> None:
    line = f"{datetime.now():%H:%M:%S.%f}"[:-4] + f" {text}"
    print(line, flush=True)
    with open(OUT / "reboot.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run(cmd: list[str], timeout: float = 20) -> str:
    try:
        done = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return (done.stdout + done.stderr).decode("utf-8", errors="replace").strip()
    except Exception as error:
        return f"{type(error).__name__}: {error}"


def ssid() -> str:
    for line in run(["netsh", "wlan", "show", "interfaces"]).splitlines():
        if line.strip().startswith("SSID") and "BSSID" not in line:
            return line.split(":", 1)[1].strip()
    return "-"


def health(host: str, timeout: float = 1.0) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://{host}:8780/health", timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return None


def cable(command: str) -> str:
    return run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "bioreactor", command], timeout=30)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    result: dict = {"started": datetime.now().isoformat(timespec="seconds"), "school_wifi": SCHOOL}
    start = time.time()
    client = None
    try:
        log(f"laptop Wi-Fi now: {ssid()}; school Wi-Fi -> connect manually (for the test only)")
        log(run(["netsh", "wlan", "set", "profileparameter", f"name={SCHOOL}", "connectionmode=manual"]))
        # «netsh wlan connect» only works for networks in Windows' last scan; while on the 5 GHz school network the
        # 2.4 GHz BioReactor-Pi may be missing from it — ask again every 3 s until Windows has rescanned
        for attempt in range(30):
            answer = run(["netsh", "wlan", "connect", f"name={PI_WIFI}"])
            if attempt == 0 or attempt % 5 == 0:
                log(f"connect to {PI_WIFI} (attempt {attempt + 1}): {answer}")
            time.sleep(3)
            if ssid() == PI_WIFI and health("10.42.0.1"):
                break
        else:
            log("could not join BioReactor-Pi before the test — stop")
            result["ok"] = False
            return 1
        log("laptop on BioReactor-Pi, the Pi answers at 10.42.0.1")
        config = json.loads((ROOT / "data/config/reactor_hardware.json").read_text(encoding="utf-8"))
        config.update({"mode": "auto", "client_log": "reports/pi_wifi/reboot_client.log",
                       "pi_candidates": [c for c in config["pi_candidates"] if c["route"] != "cable"]})
        client = ReactorClient(config)
        client.pi_url = config["pi_candidates"][0]["url"]
        client.start()
        for _ in range(20):
            if client.status()["link"]["ok"]:
                break
            time.sleep(0.5)
        log(f"client before the reboot: route={client.status()['source']['route']} link={client.status()['link']['ok']}")

        log("REBOOT over the cable: sudo systemctl reboot")
        cable("sudo -n systemctl reboot")
        t_reboot = time.time()
        marks: dict[str, float] = {}
        gone = False
        last_ssid = None
        while time.time() - start < MAX_S:
            now = time.time()
            name = ssid()
            if name != last_ssid:
                log(f"laptop Wi-Fi: {name}")
                last_ssid = name
                if gone and name == PI_WIFI and "laptop_joined" not in marks:
                    marks["laptop_joined"] = now
            status = client.status()
            ok = status["link"]["ok"]
            if not gone and not health("10.42.0.1", 0.7) and not ok:
                gone = True
                marks["pi_gone"] = now
                log("the Pi is gone (rebooting)")
            if gone and "health" not in marks and health("10.42.0.1", 0.7):
                marks["health"] = now
                log("/health answers at 10.42.0.1")
            readings = {k: v["value"] for k, v in status["readings"].items()}
            if (gone and ok and status["source"].get("route") == "pi_wifi"
                    and status["source"].get("arduino_port") not in (None, "virtual") and readings.get("gas_in") is not None):
                marks["first_data"] = now
                log(f"FIRST DATA via Wi-Fi Pi: {readings}")
                break
            time.sleep(max(0.0, 0.5 - (time.time() - now)))
        else:
            log("TIMEOUT: no data via Wi-Fi Pi")
        pi = cable("cat /proc/uptime; journalctl -b -o short-monotonic --no-pager | grep -E "
                   "'Started Wi-Fi Hotspot|BioReactor Pi bridge on|AP-STA-CONNECTED|arduino' | head -6")
        fetched = time.time()
        log(f"Pi (over the cable):\n{pi}")
        uptime = float(pi.split()[0]) if pi and pi.split()[0].replace(".", "", 1).isdigit() else None
        result["marks_from_reboot_command_s"] = {k: round(v - t_reboot, 1) for k, v in marks.items()}
        if uptime is not None:
            kernel = fetched - uptime
            result["marks_from_kernel_start_s"] = {k: round(v - kernel, 1) for k, v in marks.items() if v > kernel}
            result["first_data_from_power_on_s"] = (round(marks["first_data"] - kernel + BOOTLOADER_S, 1)
                                                    if "first_data" in marks else None)
        result["pi_log"] = pi
        result["ok"] = "first_data" in marks
        log(f"RESULT: {json.dumps({k: v for k, v in result.items() if k != 'pi_log'}, ensure_ascii=False)}")
        return 0 if result["ok"] else 1
    finally:
        if client:
            client.stop()
        log(run(["netsh", "wlan", "set", "profileparameter", f"name={SCHOOL}", "connectionmode=auto"]))
        for attempt in range(6):
            log(run(["netsh", "wlan", "connect", f"name={SCHOOL}"]))
            time.sleep(8)
            if ssid() == SCHOOL:
                break
        log(f"laptop Wi-Fi at the end: {ssid()}")
        (OUT / "reboot.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
