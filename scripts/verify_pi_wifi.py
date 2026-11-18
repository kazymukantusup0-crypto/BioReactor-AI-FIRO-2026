"""Step-6 check «no cable, no internet»: the laptop on the Pi's own Wi-Fi BioReactor-Pi.

Runs on the laptop by itself (the laptop has no internet during the test, so nobody can watch it live):

    .venv\\Scripts\\python scripts/verify_pi_wifi.py --wait 1200      waits until 10.42.0.1 answers, then checks
    .venv\\Scripts\\python scripts/verify_pi_wifi.py --now            checks at once (any route), for a dry run

Checks, written to reports/pi_wifi/verify.json + verify.log + reactor.png:
    1. the Pi answers at 10.42.0.1 (its own Wi-Fi) and the probation is confirmed over THIS network
       (ssh bio@10.42.0.1 "touch /tmp/bioreactor-hotspot-ok"), Pi side: active network, bioreactor-wifi log
    2. no internet on the laptop (TCP 1.1.1.1:443 and DNS github.com fail)
    3. the dashboard (default http://127.0.0.1:8766, mode auto) shows real Arduino data via «Wi-Fi Pi»
    4. the AI agent answers: a reactor question (Python, live data) and a calculation (local LLM, offline)
    5. a screenshot of the «Реактор» page
"""
from __future__ import annotations

import argparse
import json
import socket
import subprocess
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/pi_wifi"
PI = "10.42.0.1"
KEY = Path.home() / ".ssh/id_ed25519_bioreactor"


def log(line: str) -> None:
    text = f"{datetime.now():%H:%M:%S} {line}"
    print(text, flush=True)
    with open(OUT / "verify.log", "a", encoding="utf-8") as f:
        f.write(text + "\n")


def http_json(url: str, body: dict | None = None, timeout: float = 5) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method="POST" if body is not None else "GET",
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def pi_answers() -> bool:
    try:
        return bool(http_json(f"http://{PI}:8780/health", timeout=2).get("ok"))
    except Exception:
        return False


def run(cmd: list[str], timeout: float = 30) -> str:
    try:
        done = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return (done.stdout + done.stderr).decode("utf-8", errors="replace").strip()
    except Exception as error:
        return f"{type(error).__name__}: {error}"


def ssh(command: str) -> str:
    return run(["ssh", "-i", str(KEY), "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
                "-o", "StrictHostKeyChecking=accept-new", f"bio@{PI}", command])


def wifi_name() -> str:
    text = run(["netsh", "wlan", "show", "interfaces"])
    for line in text.splitlines():
        if line.strip().startswith("SSID") and "BSSID" not in line:
            return line.split(":", 1)[1].strip()
    return "?"


def internet() -> dict:
    out = {}
    try:
        socket.create_connection(("1.1.1.1", 443), timeout=3).close()
        out["tcp_1.1.1.1"] = "reachable"
    except OSError as error:
        out["tcp_1.1.1.1"] = f"no ({type(error).__name__})"
    try:
        socket.getaddrinfo("github.com", 443)
        out["dns_github"] = "resolved"
    except OSError as error:
        out["dns_github"] = f"no ({type(error).__name__})"
    out["no_internet"] = out["tcp_1.1.1.1"].startswith("no") and out["dns_github"].startswith("no")
    return out


def ask_agent(base: str, text: str, timeout: float) -> dict:
    """POST /api/agent/chat (server-sent events) -> the «answer» event."""
    request = urllib.request.Request(f"{base}/api/agent/chat", method="POST",
                                     data=json.dumps({"message": text, "use_llm": True}).encode(),
                                     headers={"Content-Type": "application/json"})
    started = time.time()
    answer = None
    with urllib.request.urlopen(request, timeout=timeout) as response:
        for raw in response:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            event = json.loads(line[5:].strip())
            if event.get("type") == "answer":
                answer = event
            if event.get("type") in ("done", "error"):
                if event.get("type") == "error":
                    answer = answer or {"error": event.get("message")}
                break
    answer = answer or {"error": "no answer event"}
    return {"question": text, "seconds": round(time.time() - started, 1), "mode": answer.get("mode"),
            "tools": answer.get("tools"), "text": (answer.get("explanation") or answer.get("error") or "")[:900]}


def screenshot(base: str) -> str:
    script = ROOT / "frontend/.pi_wifi_shot.tmp.mjs"   # next to node_modules (playwright-core)
    script.write_text(
        "import { chromium } from 'playwright-core'\n"
        "const b = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true })\n"
        "const p = await (await b.newContext({ viewport: { width: 1366, height: 900 } })).newPage()\n"
        f"await p.goto('{base}/dashboard/#/reactor')\n"
        "await p.getByTestId('rx-reading-temp_c').waitFor(); await p.waitForTimeout(3000)\n"
        "console.log(await p.getByTestId('rx-source').textContent())\n"
        f"await p.screenshot({{ path: '{(OUT / 'reactor.png').as_posix()}' }})\n"
        "await b.close()\n", encoding="utf-8")
    try:
        return run(["node", str(script)], timeout=60)
    finally:
        script.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait", type=int, default=0, help="seconds to wait for the Pi's Wi-Fi")
    parser.add_argument("--now", action="store_true")
    parser.add_argument("--dashboard", default="http://127.0.0.1:8766")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    result: dict = {"started": datetime.now().isoformat(timespec="seconds")}
    log("start; waiting for the Pi at 10.42.0.1" if args.wait else "start (--now)")
    deadline = time.time() + args.wait
    last_note = 0.0
    while args.wait and not pi_answers():
        if time.time() > deadline:
            log("TIMEOUT: the Pi never answered at 10.42.0.1")
            result["ok"] = False
            (OUT / "verify.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
            return 1
        if time.time() - last_note > 30:
            log(f"still waiting; laptop Wi-Fi: {wifi_name()}")
            last_note = time.time()
        time.sleep(2)
    result["laptop_wifi"] = wifi_name()
    result["pi_wifi_answers"] = pi_answers()
    log(f"Pi answers at {PI}: {result['pi_wifi_answers']}; laptop Wi-Fi: {result['laptop_wifi']}")
    if result["pi_wifi_answers"]:
        result["confirm"] = ssh("touch /tmp/bioreactor-hotspot-ok && echo confirmed")
        log(f"probation confirmation over {PI}: {result['confirm']}")
        result["pi_side"] = ssh("nmcli -f NAME,DEVICE,STATE con show --active; "
                                "journalctl -u bioreactor-wifi -n 15 --no-pager -o short-iso")
    result["internet"] = internet()
    log(f"internet: {result['internet']}")
    base = args.dashboard
    status = {}
    for _ in range(40):                       # the dashboard switches to 10.42.0.1 after the old route fails
        try:
            status = http_json(f"{base}/api/reactor/status")
            if status.get("link", {}).get("ok") and (args.now or status["source"].get("route") == "pi_wifi"):
                break
        except Exception as error:
            status = {"error": str(error)}
        time.sleep(2)
    result["dashboard"] = {k: status.get(k) for k in ("source", "link", "auto", "limits")} | {
        "readings": {k: v["value"] for k, v in status.get("readings", {}).items()},
        "relays": {k: v["on"] for k, v in status.get("relays", {}).items()},
        "alarms": [a["code"] for a in status.get("alarms", [])]}
    log(f"dashboard: {json.dumps(result['dashboard'], ensure_ascii=False)}")
    try:
        result["check_button"] = http_json(f"{base}/api/reactor/check", {}, timeout=15)
    except Exception as error:
        result["check_button"] = {"error": str(error)}
    log(f"«Проверить связь»: {result['check_button']}")
    result["agent"] = []
    for question, timeout in (("Что сейчас в реакторе?", 60),
                              ("Сколько биогаза в сутки даст 100 кг коровьего навоза?", 300)):
        try:
            result["agent"].append(ask_agent(base, question, timeout))
        except Exception as error:
            result["agent"].append({"question": question, "error": f"{type(error).__name__}: {error}"})
        log(f"agent: {json.dumps(result['agent'][-1], ensure_ascii=False)[:600]}")
    result["screenshot_badge"] = screenshot(base)
    log(f"screenshot: {result['screenshot_badge']}")
    d = result["dashboard"]
    checks = {
        "pi_on_own_wifi": bool(result["pi_wifi_answers"]),
        "probation_confirmed": "confirmed" in result.get("confirm", ""),
        "no_internet": result["internet"]["no_internet"],
        "dashboard_route_pi_wifi": (d.get("source") or {}).get("route") == "pi_wifi",
        "real_arduino": (d.get("source") or {}).get("arduino_port") not in (None, "virtual") and bool((d.get("link") or {}).get("ok")),
        "agent_reactor_answer": any(a.get("mode") == "reactor" and "ARDUINO" in a.get("text", "") for a in result["agent"]),
        "agent_llm_answer": any(a.get("question", "").startswith("Сколько") and a.get("text") and not a.get("error") for a in result["agent"]),
    }
    if args.now:
        checks = {k: v for k, v in checks.items() if k in ("real_arduino", "agent_reactor_answer", "agent_llm_answer")}
    result["checks"] = checks
    result["ok"] = all(checks.values())
    log(f"CHECKS: {checks} -> {'ALL OK' if result['ok'] else 'SOME FAILED'}")
    (OUT / "verify.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
