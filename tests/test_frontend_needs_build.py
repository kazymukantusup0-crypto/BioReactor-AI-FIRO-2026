"""ЗАПУСК_BioReactor.bat rebuilds the UI when frontend/src is newer than frontend/dist."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from frontend_needs_build import needs_build  # noqa: E402


def test_missing_stale_and_fresh_build(tmp_path):
    (tmp_path / "src").mkdir()
    source = tmp_path / "src" / "App.tsx"
    source.write_text("x", encoding="utf-8")
    assert needs_build(tmp_path)                      # no dist at all
    (tmp_path / "dist").mkdir()
    built = tmp_path / "dist" / "index.html"
    built.write_text("x", encoding="utf-8")
    os.utime(source, (1000, 1000)); os.utime(built, (2000, 2000))
    assert not needs_build(tmp_path)                  # build newer than sources
    os.utime(source, (3000, 3000))
    assert needs_build(tmp_path)                      # sources changed after the build
