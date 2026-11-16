"""HTTP API of agent v10 (added next to the old dashboard endpoints).

    POST /api/agent/chat                      SSE stream of thinking-feed events
    GET  /api/agent/conversations/{id}        facts, messages, last answer
    POST /api/agent/conversations/{id}/facts  edit facts ("What the agent knows" panel)
    POST /api/agent/reset                     forget a conversation
    GET  /api/agent/status                    model, offline, GPU share (for the UI indicator)
    GET  /api/agent/demo-reactor              defaults used when the user did not give a value

SSE format: every event is sent as
    event: <type>
    data: <json>
"""
from __future__ import annotations

from typing import Literal

import json
import threading
import time
from collections.abc import Iterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.agent_v10.agent import Agent
from src.agent_v10.config import demo_reactor
from src.agent_v10.version import server_version
from src.agent_v10.facts import EMPTY_FACTS, apply_overrides
from src.agent_v10.keepalive import KeepAlive, interval_from_env, ping
from src.agent_v10.memory import Memory


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9_-]{8,64}$")
    use_llm: bool = True
    # The interface language switch (RU / ҚАЗ / EN); the agent still answers in the language of the message.
    ui_language: Literal["ru", "kk", "en"] | None = None


class ResetRequest(BaseModel):
    conversation_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{8,64}$")


class FactsRequest(BaseModel):
    facts: dict


NUMBER_FACTS = {"reactor_volume_l": (1, 1_000_000), "ambient_c": (-60, 60), "target_c": (5, 70), "days": (1, 365)}
CHOICE_FACTS = {"insulation": {"none", "basic", "good"}, "operating_mode": {"batch", "continuous"},
                "price_class": {"household", "business"}}


def fact_error(key: str, value) -> str | None:
    """Why a value typed in the 'What the agent knows' panel is not accepted (None = fine)."""
    if value is None:
        return None
    if key in NUMBER_FACTS:
        low, high = NUMBER_FACTS[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
            return f"{key} must be a number from {low} to {high}"
    if key in CHOICE_FACTS and value not in CHOICE_FACTS[key]:
        return f"{key} must be one of {sorted(CHOICE_FACTS[key])}"
    if key == "components" and not isinstance(value, list):
        return "components must be a list"
    return None


def sse(event: dict) -> str:
    """Format one event for Server-Sent Events."""
    return f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


def create_router(agent: Agent | None = None) -> APIRouter:
    """Router factory; tests pass their own Agent (temporary DB, fake LLM)."""
    router = APIRouter(prefix="/api/agent", tags=["agent v10"])
    holder: dict = {"agent": agent}
    busy = {"active": 0, "last_used": time.monotonic()}  # chat streams in progress, end of the last one
    busy_lock = threading.Lock()

    def get_agent() -> Agent:
        if holder["agent"] is None:
            holder["agent"] = Agent()
        return holder["agent"]

    interval = interval_from_env()
    if interval:
        # Demo mode (ЗАПУСК_BioReactor.bat): keep the model and the GPU awake between questions.
        holder["keepalive"] = KeepAlive(interval, is_busy=lambda: busy["active"] > 0,
                                        last_used=lambda: busy["last_used"],
                                        do_ping=lambda: ping(get_agent().llm)).start()

    @router.post("/chat")
    def chat(body: ChatRequest) -> StreamingResponse:
        conversation_id = body.conversation_id or Memory.new_id()

        def stream() -> Iterator[str]:
            with busy_lock:
                busy["active"] += 1
                waiting = busy["active"] > 1
            try:
                if waiting and body.use_llm:
                    # Ollama answers one request at a time: a second chat waits in a queue and looks
                    # twice as slow (measured: 4.5 s -> 8.7 s, docs/benchmark.md). Say so instead of hiding it.
                    yield sse({"type": "note", "code": "llm_busy",
                               "message": "Модель сейчас отвечает на другой запрос — этот ответ будет в очереди"})
                for event in get_agent().run(conversation_id, body.message, use_llm=body.use_llm,
                                                 ui_language=body.ui_language):
                    yield sse(event)
            except Exception as error:  # the stream must always end with a clear event
                yield sse({"type": "error", "message": f"{type(error).__name__}: {error}"})
                yield sse({"type": "done", "mode": "error"})
            finally:
                with busy_lock:
                    busy["active"] -= 1
                    busy["last_used"] = time.monotonic()

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Conversation-Id": conversation_id})

    @router.get("/conversations/{conversation_id}")
    def conversation(conversation_id: str) -> dict:
        return get_agent().memory.get(conversation_id)

    @router.post("/conversations/{conversation_id}/facts")
    def edit_facts(conversation_id: str, body: FactsRequest) -> dict:
        unknown = set(body.facts) - set(EMPTY_FACTS)
        if unknown:
            return {"ok": False, "error": f"unknown facts: {sorted(unknown)}"}
        errors = [error for key, value in body.facts.items() if (error := fact_error(key, value))]
        if errors:
            return {"ok": False, "error": "; ".join(errors)}
        memory = get_agent().memory
        merged = apply_overrides(memory.get(conversation_id)["facts"], body.facts)
        return {"ok": True, **memory.update_facts(conversation_id, merged)}

    @router.post("/reset")
    def reset(body: ResetRequest) -> dict:
        get_agent().memory.reset(body.conversation_id)
        return {"ok": True, "conversation_id": body.conversation_id}

    @router.get("/status")
    def status() -> dict:
        llm = get_agent().llm
        available = llm.available()
        keepalive = holder.get("keepalive")
        return {"model": llm.model, "llm_available": available, "offline": True, "version": server_version(),
                "mode": "llm" if available else "no_llm", "gpu": llm.gpu_status() if available else {"loaded": False},
                "keepalive": {"interval_s": keepalive.interval, "pings": keepalive.pings, "errors": keepalive.errors}
                if keepalive else None}

    @router.get("/demo-reactor")
    def demo() -> dict:
        return demo_reactor()

    return router
