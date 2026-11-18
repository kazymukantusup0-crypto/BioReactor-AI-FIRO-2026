"""Watch a Wi-Fi test of the Pi's own network over the DIRECT CABLE, without internet on the laptop.

    .venv\\Scripts\\python scripts/watch_pi_wifi.py --minutes 25

Every 5 s, written to reports/pi_wifi/watch.log (new lines only, so it stays readable):
    Pi (ssh over 192.168.50.2): active networks, wlan0 mode/channel, devices on the own Wi-Fi, DHCP leases,
                                new lines of NetworkManager / wpa_supplicant / bioreactor-wifi logs
    laptop: Wi-Fi state, network name, authentication and cipher Windows uses, its addresses
"""
from __future__ import annotations

import argparse
import subprocess
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/pi_wifi"
KEY = Path.home() / ".ssh/id_ed25519_bioreactor"
PI_COMMAND = (
    "echo '## active'; nmcli -t -f NAME,DEVICE,STATE con show --active; "
    "echo '## wlan0'; nmcli -g GENERAL.STATE,GENERAL.CONNECTION device show wlan0; /usr/sbin/iw dev wlan0 info | grep -E 'type|channel|ssid'; "
    "echo '## devices'; /usr/sbin/iw dev wlan0 station dump 2>&1 | grep -E '^Station|signal:|authorized' ; "
    "echo '## leases'; cat /var/lib/NetworkManager/dnsmasq-wlan0.leases 2>&1; "
    "echo '## logs'; journalctl -u NetworkManager -u wpa_supplicant -u bioreactor-wifi -t bioreactor-wifi "
    "--since '-15 sec' --no-pager -o short-iso 2>&1 | grep -v -- '-- No entries --'"
)


def run(cmd: list[str], timeout: float = 20) -> str:
    try:
        done = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return (done.stdout + done.stderr).decode("utf-8", errors="replace").strip()
    except Exception as error:
        return f"{type(error).__name__}: {error}"


def laptop() -> str:
    text = run(["netsh", "wlan", "show", "interfaces"])
    keep = [line.strip() for line in text.splitlines()
            if line.strip().split(":")[0].strip() in {"State", "SSID", "Authentication", "Cipher", "Signal", "Radio type", "Channel",
                                                      "Состояние", "Проверка подлинности", "Шифр", "Сигнал", "Тип радио", "Канал"}]
    ips = run(["powershell", "-NoProfile", "-Command",
               "Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' } | "
               "ForEach-Object { $_.InterfaceAlias + ' ' + $_.IPAddress }"])
    return "\n".join(keep) + "\n## laptop addresses\n" + ips


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--minutes", type=float, default=25)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    log = OUT / "watch.log"
    seen: set[str] = set()
    last_block = ""
    end = time.time() + args.minutes * 60
    with open(log, "a", encoding="utf-8") as f:
        f.write(f"\n===== watch started {datetime.now():%Y-%m-%d %H:%M:%S} for {args.minutes} min\n")
    while time.time() < end:
        pi = run(["ssh", "-i", str(KEY), "-o", "BatchMode=yes", "-o", "ConnectTimeout=4", "bio@192.168.50.2", PI_COMMAND])
        state = f"## PI\n{pi}\n## LAPTOP\n{laptop()}"
        # log lines are printed once; the rest of the picture only when it changes
        lines = []
        for line in state.splitlines():
            if line[:4].isdigit() and "T" in line[:12]:          # a journal line (short-iso)
                if line in seen:
                    continue
                seen.add(line)
            lines.append(line)
        block = "\n".join(lines)
        picture = "\n".join(l for l in lines if not (l[:4].isdigit() and "T" in l[:12]))
        if picture != last_block or len(block) != len(picture):
            with open(log, "a", encoding="utf-8") as f:
                f.write(f"\n--- {datetime.now():%H:%M:%S}\n{block}\n")
            last_block = picture
        time.sleep(5)
    with open(log, "a", encoding="utf-8") as f:
        f.write(f"===== watch ended {datetime.now():%H:%M:%S}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
