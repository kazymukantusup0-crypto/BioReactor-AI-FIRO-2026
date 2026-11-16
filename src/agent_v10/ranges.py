"""Range arithmetic: every uncertain value is a dict {"low": x, "high": y}.

The basic operations are reused from the existing science core
(src/estimation/scenario_ranges.py and src/economics/energy_conversion.py),
so the agent uses exactly the same arithmetic as the rest of the project.
"""
from __future__ import annotations

from src.economics.energy_conversion import add, subtract
from src.estimation.scenario_ranges import multiply, point, scale

__all__ = ["add", "subtract", "multiply", "point", "scale", "divide", "make", "mid", "total", "display",
           "display_range", "tidy", "fmt", "range_text"]


def make(low: float, high: float) -> dict:
    """Build a range and make sure low <= high."""
    return {"low": min(low, high), "high": max(low, high)}


def divide(a: dict, b: dict) -> dict:
    """Range division a / b (b must be positive): smallest = a.low / b.high."""
    return {"low": a["low"] / b["high"], "high": a["high"] / b["low"]}


def mid(a: dict) -> float:
    """Middle of a range."""
    return (a["low"] + a["high"]) / 2


def total(ranges: list[dict]) -> dict:
    """Sum of several ranges."""
    result = point(0.0)
    for item in ranges:
        result = add(result, item)
    return result


def display(value: float) -> float:
    """Round a number the way it is shown to the user and to the LLM.

    The same rounding is used by the number check in answer.py, so a number
    written by the LLM can be matched to a tool result.
        0.0123 -> 0.012   4.567 -> 4.6   45.67 -> 46   4567 -> 4570
    """
    magnitude = abs(value)
    if magnitude == 0:
        return 0.0
    if magnitude < 1:
        return round(value, 2)
    if magnitude < 10:
        return round(value, 1)
    if magnitude < 1000:
        return float(round(value))
    return float(round(value, -1))


def tidy(value: float) -> float | int:
    """52.0 -> 52, 2.9 -> 2.9 (integers look cleaner in text and JSON)."""
    rounded = display(value)
    return int(rounded) if rounded == int(rounded) else rounded


def fmt(value: float) -> str:
    """Number as text for the user: 200.0 -> '200', 2.94 -> '2.9'."""
    return str(tidy(value))


def plain(value: float) -> str:
    """Like f"{value:g}" but never in exponent form: 1000000 -> '1000000', not '1e+06' (manual check 3, P)."""
    text = f"{value:g}"
    if "e" in text:
        text = f"{float(value):.0f}" if abs(value) >= 1 else f"{float(value):.6f}".rstrip("0").rstrip(".")
    return text


def display_range(a: dict) -> dict:
    """Rounded copy of a range, for the LLM and the UI cards."""
    return {"low": display(a["low"]), "high": display(a["high"])}


def _signed(value) -> str:
    return f"−{abs(value)}" if value < 0 else f"{value}"


def range_text(values: list) -> str:
    """[2.9, 5.2] -> '2.9–5.2';  [-1200, -377] -> '−1200 … −377' (a dash would look like a minus)."""
    low, high = values
    if low == high:
        return _signed(low)
    if low < 0 or high < 0:
        return f"{_signed(low)} … {_signed(high)}"
    return f"{low}–{high}"


def center(values: list) -> float | int:
    """Central estimate of a displayed range: [2.9, 5.2] -> 4 (rounded like every other number)."""
    low, high = values
    return tidy((low + high) / 2)


def approx_text(values: list) -> str:
    """'≈4 (2.9–5.2)'; a single value stays as it is: [52, 52] -> '52'."""
    low, high = values
    if low == high:
        return _signed(low)
    return f"≈{_signed(center(values))} ({range_text(values)})"
