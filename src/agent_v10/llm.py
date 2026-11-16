"""Ollama client: /api/chat with native tool calling and streaming.

Settings (model, num_ctx, think, keep_alive, num_gpu) come from
data/config/llm_selection.json. Only the Python standard library is used.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Iterator

from src.agent_v10.config import llm_settings


class LLMUnavailable(RuntimeError):
    """Ollama is not running, the model is missing, or the request failed."""


class OllamaClient:
    """Thin wrapper around Ollama's HTTP API."""

    def __init__(self, model: str | None = None, base_url: str | None = None, timeout: float = 120.0):
        settings = llm_settings()
        self.model = model or settings["model"]
        self.base_url = (base_url or settings["ollama_url"]).rstrip("/")
        self.timeout = timeout
        # num_predict caps one reply: 2–4 sentences need ~60–180 tokens (a Russian or Kazakh word
        # takes 2–3 tokens). At ~50 tokens/s, 300 tokens = 6 s at most; an unfinished last sentence
        # is cut off by answer.trim_to_sentence. The jury reads the cards, not a long text.
        self.options = {"num_ctx": settings["num_ctx"], "num_gpu": settings["num_gpu"], "temperature": 0.2,
                        "num_predict": settings.get("num_predict", 300)}
        self.think = settings["think"]
        self.keep_alive = settings["keep_alive"]

    def available(self, timeout: float = 2.0) -> bool:
        """True if Ollama answers and the model is installed."""
        try:
            with urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=timeout) as response:
                models = json.loads(response.read().decode("utf-8")).get("models", [])
        except (OSError, ValueError):
            return False
        names = {m.get("name") for m in models} | {m.get("model") for m in models}
        return self.model in names or f"{self.model}:latest" in names

    def gpu_status(self) -> dict:
        """Same information as `ollama ps`: share of the model in VRAM."""
        try:
            with urllib.request.urlopen(f"{self.base_url}/api/ps", timeout=2) as response:
                loaded = json.loads(response.read().decode("utf-8")).get("models", [])
        except (OSError, ValueError):
            return {"loaded": False}
        # Other models in VRAM (old chat, benchmark, `ollama run`) push ours out or onto the CPU:
        # the next answer then waits ~5 s for a reload (docs/benchmark.md, "Почему ответ был 10 с").
        others = sorted({m.get("name") for m in loaded} - {self.model, f"{self.model}:latest"} - {None})
        for model in loaded:
            if model.get("name") == self.model or model.get("model") == self.model:
                size = model.get("size") or 0
                vram = model.get("size_vram") or 0
                return {"loaded": True, "gpu_percent": round(100 * vram / size) if size else 0,
                        "context": model.get("context_length"), "vram_gb": round(vram / 1e9, 2), "others": others}
        return {"loaded": False, "others": others}

    def chat_stream(self, messages: list[dict], tools: list[dict] | None = None) -> Iterator[dict]:
        """Stream one chat step.

        Yields {"type": "token", "text": ...} for answer text and finally
        {"type": "final", "content": str, "tool_calls": [...], "stats": {...}}.
        """
        payload = {
            "model": self.model, "messages": messages, "stream": True, "think": self.think,
            "keep_alive": self.keep_alive, "options": self.options,
        }
        if tools:
            payload["tools"] = tools
        request = urllib.request.Request(f"{self.base_url}/api/chat", data=json.dumps(payload).encode("utf-8"),
                                         headers={"Content-Type": "application/json"})
        started = time.perf_counter()
        first_token_ms = None
        content_parts: list[str] = []
        tool_calls: list[dict] = []
        final_chunk: dict = {}
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                for line in response:
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    if chunk.get("error"):
                        raise LLMUnavailable(str(chunk["error"]))
                    message = chunk.get("message") or {}
                    text = message.get("content") or ""
                    if text:
                        if first_token_ms is None:
                            first_token_ms = round((time.perf_counter() - started) * 1000)
                        content_parts.append(text)
                        yield {"type": "token", "text": text}
                    tool_calls.extend(message.get("tool_calls") or [])
                    if chunk.get("done"):
                        final_chunk = chunk
        except (urllib.error.URLError, OSError, ValueError) as error:
            raise LLMUnavailable(str(error)) from error
        eval_seconds = (final_chunk.get("eval_duration") or 0) / 1e9
        yield {
            "type": "final",
            "content": "".join(content_parts),
            "tool_calls": tool_calls,
            "stats": {
                "duration_ms": round((time.perf_counter() - started) * 1000),
                "first_token_ms": first_token_ms,
                "prompt_tokens": final_chunk.get("prompt_eval_count"),
                "output_tokens": final_chunk.get("eval_count"),
                "tokens_per_s": round(final_chunk.get("eval_count", 0) / eval_seconds, 1) if eval_seconds else None,
            },
        }
