"""Exit code 0 if frontend/dist must be (re)built, 1 if the build is up to date.

Used by start.bat: frontend/dist is not in git, so after `git pull` the old build
would still be served. The build is stale when any file in frontend/src,
frontend/index.html or the package/vite configs is newer than dist/index.html.
"""
from __future__ import annotations

import sys
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
INPUTS = ["src", "index.html", "package.json", "package-lock.json", "vite.config.ts", "public"]


def newest_input_mtime(frontend: Path = FRONTEND) -> float:
    newest = 0.0
    for name in INPUTS:
        path = frontend / name
        files = [path] if path.is_file() else (p for p in path.rglob("*") if p.is_file()) if path.is_dir() else []
        for file in files:
            newest = max(newest, file.stat().st_mtime)
    return newest


def needs_build(frontend: Path = FRONTEND) -> bool:
    built = frontend / "dist" / "index.html"
    return not built.exists() or newest_input_mtime(frontend) > built.stat().st_mtime


if __name__ == "__main__":
    sys.exit(0 if needs_build() else 1)
