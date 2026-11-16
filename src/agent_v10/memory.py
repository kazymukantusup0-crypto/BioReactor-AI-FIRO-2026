"""Dialogue memory in SQLite: facts about the batch/reactor and the last messages.

One row per conversation. Facts survive between messages and app restarts,
so the agent does not ask again what it already knows.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from src.agent_v10.config import MEMORY_DB_PATH
from src.agent_v10.facts import empty_facts

# How many previous messages (user + assistant) are sent to the LLM.
HISTORY_MESSAGES = 6


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Memory:
    """Small SQLite store. Each method opens its own short connection (thread-safe)."""

    def __init__(self, path: Path | str = MEMORY_DB_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS agent_v10_conversations ("
                " id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,"
                " language TEXT NOT NULL DEFAULT 'ru', facts_json TEXT NOT NULL,"
                " messages_json TEXT NOT NULL, last_answer_json TEXT)"
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Open, commit and ALWAYS close (on Windows an open connection locks the file)."""
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            with connection:  # commits on success, rolls back on error
                yield connection
        finally:
            connection.close()

    @staticmethod
    def new_id() -> str:
        return uuid.uuid4().hex

    def get(self, conversation_id: str) -> dict:
        """Conversation state; a new empty one if the id is unknown."""
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM agent_v10_conversations WHERE id = ?", (conversation_id,)).fetchone()
        if row is None:
            return {"id": conversation_id, "language": "ru", "facts": empty_facts(), "messages": [],
                    "last_answer": None, "exists": False}
        return {
            "id": row["id"], "language": row["language"], "facts": json.loads(row["facts_json"]),
            "messages": json.loads(row["messages_json"]),
            "last_answer": json.loads(row["last_answer_json"]) if row["last_answer_json"] else None,
            "created_at": row["created_at"], "updated_at": row["updated_at"], "exists": True,
        }

    def save(self, conversation_id: str, *, facts: dict, messages: list[dict], language: str,
             last_answer: dict | None = None) -> None:
        """Insert or update a conversation."""
        now = _now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO agent_v10_conversations (id, created_at, updated_at, language, facts_json, messages_json, last_answer_json)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at, language = excluded.language,"
                " facts_json = excluded.facts_json, messages_json = excluded.messages_json,"
                " last_answer_json = COALESCE(excluded.last_answer_json, last_answer_json)",
                (conversation_id, now, now, language, json.dumps(facts, ensure_ascii=False),
                 json.dumps(messages, ensure_ascii=False),
                 json.dumps(last_answer, ensure_ascii=False) if last_answer else None),
            )

    def update_facts(self, conversation_id: str, facts: dict) -> dict:
        """Replace the facts (the UI panel 'What the agent knows' edits them)."""
        state = self.get(conversation_id)
        self.save(conversation_id, facts=facts, messages=state["messages"], language=state["language"])
        return self.get(conversation_id)

    def reset(self, conversation_id: str) -> None:
        """Forget a conversation completely."""
        with self._connect() as connection:
            connection.execute("DELETE FROM agent_v10_conversations WHERE id = ?", (conversation_id,))

    @staticmethod
    def history(messages: list[dict]) -> list[dict]:
        """The last messages to send to the LLM."""
        return messages[-HISTORY_MESSAGES:]
