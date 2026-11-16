"""Tool search_knowledge: short quotes with source names from the local base.

Reuses the existing verified local catalogue
(src/recommendations/knowledge.search_scientific_sources over data/knowledge)
plus the temperature regime sources. No internet search.
"""
from __future__ import annotations

from src.agent_v10.config import temperature_regimes
from src.agent_v10.tools.common import result, unique_sources
from src.recommendations.knowledge import search_scientific_sources

MAX_CLAIMS = 3
MAX_SOURCES = 4


def _claim_text(claim: dict, language: str) -> str:
    statement = claim.get("statement") or claim.get("text") or {}
    if isinstance(statement, dict):
        return statement.get(language) or statement.get("ru") or statement.get("en") or ""
    return str(statement)


def search_knowledge(query: str, substrate: str | None = None, language: str = "ru") -> dict:
    """Find claims and sources relevant to the question."""
    if not query or not query.strip():
        return result("search_knowledge", ok=False, data={"status": "empty_query"}, llm={"status": "empty_query"})
    found = search_scientific_sources(query, material=substrate)
    claims = found.get("claims", [])[:MAX_CLAIMS]
    sources = [{"id": s.get("id"), "title": s.get("title"), "year": s.get("year"), "doi": s.get("doi"),
                "url": s.get("url")} for s in found.get("sources", [])]
    if any(word in query.lower() for word in ["температур", "temperature", "режим", "regime", "температура"]):
        sources += [{"id": s["id"], "title": s["title"], "year": s.get("year"), "doi": s.get("doi"), "url": s.get("url")}
                    for s in temperature_regimes()["sources"]]
    sources = unique_sources(sources)[:MAX_SOURCES]
    quotes = [{"text": _claim_text(claim, language), "source_id": claim.get("source_id")} for claim in claims]
    data = {"status": "ok", "claims": quotes, "sources": sources, "query": query}
    llm = {
        "quotes": [quote["text"][:300] for quote in quotes],
        "sources": [f"{s['title']} ({s['year']})" if s.get("year") else s["title"] for s in sources],
        "found": bool(quotes or sources),
    }
    return result("search_knowledge", ok=bool(quotes or sources), data=data, llm=llm,
                  sources=sources, label="literature")
