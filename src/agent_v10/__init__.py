"""BioReactor AI agent v10.

A small, readable AI agent for a biogas plant:

    user message -> facts (Python) -> LLM decides which tool to call
    -> Python tool computes numbers -> LLM explains -> number check -> answer

Key rule: every number comes from a Python tool. The LLM only chooses tools
and explains their results in plain language (ru / kk / en).

Modules:
    config.py     settings shared with Ollama (data/config/llm_selection.json)
    ranges.py     low/high range arithmetic and display rounding
    units.py      litres / kg / tonnes / m3 / buckets -> L or kg
    substrates.py typical substrate properties from the reviewed profiles
    facts.py      deterministic fact extraction from free text
    tools/        the 7 calculation tools with JSON schemas
    memory.py     SQLite memory of facts and dialogue
    llm.py        Ollama /api/chat client with native tool calling
    answer.py     final answer: numbers block, number check, templates
    agent.py      the agent loop that emits "thinking feed" events
    api.py        FastAPI endpoints (SSE stream)
"""
