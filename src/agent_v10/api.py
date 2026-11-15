"""HTTP API of agent v10 (added next to the old dashboard endpoints).

    POST /api/agent/chat                      SSE stream of thinking-feed events
    GET  /api/agent/conversations/{id}        facts, messages, last answer
    POST /api/agent/conversations/{id}/facts  edit facts ("What the agent knows" panel)
    POST /api/agent/reset                     forget a conversation
    GET  /api/agent/status                    model, offline, GPU share (for the UI indicator)

SSE format: every event is sent as
    event: <type>
    data: <json>
"""
from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.agent_v10.agent import Agent
from src.agent_v10.facts import EMPTY_FACTS, apply_overrides
from src.agent_v10.memory import Memory


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9_-]{8,64}$")
    use_llm: bool = True


class ResetRequest(BaseModel):
    conversation_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{8,64}$")


class FactsRequest(BaseModel):
    facts: dict


def sse(event: dict) -> str:
    """Format one event for Server-Sent Events."""
    return f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


def create_router(agent: Agent | None = None) -> APIRouter:
    """Router factory; tests pass their own Agent (temporary DB, fake LLM)."""
    router = APIRouter(prefix="/api/agent", tags=["agent v10"])
    holder: dict = {"agent": agent}

    def get_agent() -> Agent:
        if holder["agent"] is None:
            holder["agent"] = Agent()
        return holder["agent"]

    @router.post("/chat")
    def chat(body: ChatRequest) -> StreamingResponse:
        conversation_id = body.conversation_id or Memory.new_id()

        def stream() -> Iterator[str]:
            try:
                for event in get_agent().run(conversation_id, body.message, use_llm=body.use_llm):
                    yield sse(event)
            except Exception as error:  # the stream must always end with a clear event
                yield sse({"type": "error", "message": f"{type(error).__name__}: {error}"})
                yield sse({"type": "done", "mode": "error"})

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
        return {"model": llm.model, "llm_available": available, "offline": True,
                "mode": "llm" if available else "no_llm", "gpu": llm.gpu_status() if available else {"loaded": False}}

    return router
