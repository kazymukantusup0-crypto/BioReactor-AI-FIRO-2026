"""Which code a running server uses — protection against testing a stale server (manual check 3).

    commit       short git commit (read from .git directly: git does not have to be installed)
    fingerprint  hash of size + modification time of the code the server loads: src/**/*.py, main.py, the built UI
                 (frontend/dist/index.html names the hashed bundles) and data/config/*.json. It also changes for
                 edits that are not committed yet, which the commit alone would miss.
    started_at   when this server process imported the code

ЗАПУСК_BioReactor.bat compares the fingerprint of the running server with the files on disk
(scripts/server_version.py) and restarts a stale server; the UI shows the version and warns if it is stale.
"""
from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path

from src.agent_v10.config import ROOT

STARTED_AT = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
_cache: dict = {}


def _git_dir() -> Path | None:
    git = ROOT / ".git"
    if git.is_file():  # a worktree: "gitdir: <path>"
        text = git.read_text(encoding="utf-8").strip()
        git = Path(text.split(":", 1)[1].strip()) if text.startswith("gitdir:") else git
    return git if git.is_dir() else None


def git_commit() -> dict:
    """{"commit": "933f47f", "branch": "agent-v10-fixes"} or "unknown" values."""
    git = _git_dir()
    if git is None:
        return {"commit": "unknown", "branch": "unknown"}
    try:
        head = (git / "HEAD").read_text(encoding="utf-8").strip()
        if not head.startswith("ref:"):
            return {"commit": head[:7], "branch": "detached"}
        ref = head.split(":", 1)[1].strip()
        branch = ref.removeprefix("refs/heads/")
        ref_file = git / ref
        if ref_file.is_file():
            return {"commit": ref_file.read_text(encoding="utf-8").strip()[:7], "branch": branch}
        packed = git / "packed-refs"
        for line in packed.read_text(encoding="utf-8").splitlines() if packed.is_file() else []:
            if line.endswith(" " + ref):
                return {"commit": line[:7], "branch": branch}
        return {"commit": "unknown", "branch": branch}
    except OSError:
        return {"commit": "unknown", "branch": "unknown"}


def _code_files() -> list[Path]:
    files = [ROOT / "main.py", ROOT / "frontend" / "dist" / "index.html"]
    files += [p for p in (ROOT / "src").rglob("*.py") if "__pycache__" not in p.parts]
    files += list((ROOT / "data" / "config").glob("*.json"))
    return sorted(p for p in files if p.is_file())


def fingerprint() -> str:
    """12 hex characters; recalculated at most every 5 s (≈300 files, a few ms)."""
    now = time.monotonic()
    if _cache.get("at") and now - _cache["at"] < 5:
        return _cache["value"]
    digest = hashlib.sha1()
    for path in _code_files():
        stat = path.stat()
        digest.update(f"{path.relative_to(ROOT).as_posix()}|{stat.st_size}|{stat.st_mtime_ns}\n".encode())
    _cache.update(at=now, value=digest.hexdigest()[:12])
    return _cache["value"]


# The code this process loaded: computed once at import, i.e. at server start.
LOADED = {**git_commit(), "fingerprint": fingerprint()}


def server_version() -> dict:
    """For /api/agent/status: the loaded code, the code on disk now, and whether the server is stale."""
    on_disk = {**git_commit(), "fingerprint": fingerprint()}
    return {**LOADED, "started_at": STARTED_AT, "disk_commit": on_disk["commit"],
            "disk_fingerprint": on_disk["fingerprint"], "stale": on_disk["fingerprint"] != LOADED["fingerprint"]}
