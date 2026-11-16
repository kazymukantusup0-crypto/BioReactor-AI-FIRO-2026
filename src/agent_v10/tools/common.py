"""Helpers shared by all tools: result structure, labels, sources."""
from __future__ import annotations

from src.agent_v10.ranges import tidy

LABEL_ORDER = ["measured", "literature", "assumption"]


def weakest(labels: list[str]) -> str:
    """The overall label is the weakest one: assumption < literature < measured."""
    present = [label for label in labels if label in LABEL_ORDER]
    if not present:
        return "assumption"
    return max(present, key=LABEL_ORDER.index)


def unique_sources(sources: list[dict | None]) -> list[dict]:
    """Remove duplicates (same id) and empty records, keep order."""
    seen, result = set(), []
    for source in sources:
        if not source or source.get("id") in seen:
            continue
        seen.add(source.get("id"))
        result.append(source)
    return result


def unique(items: list[str]) -> list[str]:
    """Remove duplicate strings, keep order."""
    return list(dict.fromkeys(item for item in items if item))


def pair(a: dict) -> list[float | int]:
    """Range -> [low, high] rounded for display (compact form for the LLM)."""
    return [tidy(a["low"]), tidy(a["high"])]


def result(name: str, *, ok: bool, data: dict, llm: dict, assumptions: list[str] | None = None,
           sources: list[dict] | None = None, label: str = "assumption", question: str | None = None) -> dict:
    """Build a tool result in one standard shape."""
    return {
        "name": name,
        "ok": ok,
        "data": data,
        "llm": llm,
        "assumptions": unique(assumptions or []),
        "sources": unique_sources(sources or []),
        "label": label,
        "question": question,
    }
