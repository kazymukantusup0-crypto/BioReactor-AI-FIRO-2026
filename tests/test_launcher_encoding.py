"""ЗАПУСК_BioReactor.bat must switch Python to UTF-8 before it starts any Python process.

Without it the Windows console (cp1251) crashes on "−", "→" or Kazakh letters printed by a script
(happened with scripts/eval_dialogs.py on 2026-11-16).
"""
from pathlib import Path

BAT = Path(__file__).resolve().parents[1] / "ЗАПУСК_BioReactor.bat"


def test_launcher_sets_utf8_before_first_python() -> None:
    lines = [line.strip() for line in BAT.read_text(encoding="utf-8").splitlines()]
    first_python = next(i for i, line in enumerate(lines)
                        if not line.lower().startswith(("rem", "set ")) and ("python" in line.lower() or "py -3" in line))
    for setting in ('chcp 65001 >nul', 'set "PYTHONUTF8=1"', 'set "PYTHONIOENCODING=utf-8"'):
        assert setting in lines, setting
        assert lines.index(setting) < first_python, f"{setting} must come before line {first_python + 1}"
