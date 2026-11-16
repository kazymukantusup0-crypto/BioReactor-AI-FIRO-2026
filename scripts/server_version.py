"""Is the running dashboard server using the code that is on disk now? (used by ЗАПУСК_BioReactor.bat)

    .venv/Scripts/python scripts/server_version.py --port 8765
    exit 0 — the server runs the current code
    exit 2 — the server is stale (other commit / changed files) or too old to report its version: restart it
    exit 3 — no server on this port
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

from src.agent_v10.version import fingerprint, git_commit  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    port = parser.parse_args().port
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3):
            pass
    except OSError:
        print(f"      сервера на порту {port} нет")
        return 3
    disk = {**git_commit(), "fingerprint": fingerprint()}
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/agent/status", timeout=10) as response:
            running = json.loads(response.read().decode("utf-8")).get("version")
    except (OSError, ValueError):
        running = None
    if not running:
        print(f"      на порту {port} старый сервер без версии — перезапускаю (на диске {disk['commit']})")
        return 2
    if running.get("fingerprint") != disk["fingerprint"]:
        print(f"      сервер устарел: запущен {running.get('commit')} ({running.get('started_at')}), "
              f"на диске {disk['commit']} — перезапускаю")
        return 2
    print(f"      сервер уже работает на текущем коде: {running.get('commit')}, запущен {running.get('started_at')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
