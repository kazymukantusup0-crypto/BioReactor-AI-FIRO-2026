"""«Сырьё и смеси» page: the SAME calculation as the agent in the chat.

POST /api/substrates/estimate runs the agent tool `estimate_methane` through `run_tool`, exactly as the agent does
when the user wrote the batch in the chat (facts["components"]). Nothing is recalculated here: the page and the chat
give equal numbers for equal input (tests/test_substrates_page_same_as_agent.py).

Only two things happen before the call: grams and millilitres (units the page offers, the chat parser does not)
are turned into kg and L, and the input is checked (amount > 0, at most 10⁹).
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.agent_v10 import substrates
from src.agent_v10.tools.methane import estimate_methane
from src.agent_v10.tools.registry import run_tool

# Page unit -> (agent unit, factor). The agent knows kg, t, L, m3.
UNITS = {"kg": ("kg", 1.0), "g": ("kg", 0.001), "t": ("t", 1.0), "L": ("L", 1.0), "mL": ("L", 0.001), "m3": ("m3", 1.0)}


class Component(BaseModel):
    material: str = Field(min_length=1, max_length=80)
    quantity: float = Field(gt=0, le=1_000_000_000)
    unit: Literal["kg", "g", "t", "L", "mL", "m3"]
    state: str | None = Field(default=None, max_length=40)


class EstimateRequest(BaseModel):
    components: list[Component] = Field(min_length=1, max_length=20)
    language: Literal["ru", "kk", "en"] = "ru"


def agent_components(components: list[Component]) -> list[dict]:
    """Page rows -> the facts["components"] the agent builds from the user's words."""
    out = []
    for c in components:
        unit, factor = UNITS[c.unit]
        state = None if c.state in (None, "", "unknown") else c.state
        out.append({"substrate": c.material, "amount": c.quantity * factor, "unit": unit, "state": state})
    return out


def estimate(body: EstimateRequest) -> dict:
    components = agent_components(body.components)
    answer = run_tool("estimate_methane", {}, {"components": components}, body.language)
    data = answer.get("data") or {}
    # Share of each component in the methane of the batch (for the contribution chart): middle of each range.
    rows = data.get("components") or []
    total = sum((r["methane_m3"]["low"] + r["methane_m3"]["high"]) / 2 for r in rows) or 1.0
    for r in rows:
        r["share_of_methane"] = (r["methane_m3"]["low"] + r["methane_m3"]["high"]) / 2 / total
    return {"ok": answer.get("ok", False), "status": data.get("status"), "data": data,
            "assumptions": answer.get("assumptions") or [], "sources": answer.get("sources") or [],
            "question": answer.get("question"), "label": answer.get("label"), "agent_components": components}


@lru_cache(maxsize=1)
def materials_with_data() -> list[str]:
    """Materials the agent has a yield for (its reference table). Others get an honest «no data» answer."""
    known = sorted(substrates.known_materials())
    return [m for m in known if m != "manure" and substrates.resolve_material(m) == m
            and estimate_methane([{"substrate": m, "amount": 1, "unit": "kg"}])["data"].get("status") == "ok"]


def create_router() -> APIRouter:
    router = APIRouter(prefix="/api/substrates", tags=["Substrates page (agent calculation)"])

    @router.get("/materials")
    def materials() -> dict:
        return {"with_data": materials_with_data()}

    @router.post("/estimate")
    def estimate_route(body: EstimateRequest) -> dict:
        return estimate(body)

    return router
