"""Conversation history persisted in SQLite, one row per Responses API item.

A customer who closes the browser and comes back with the same link sees the conversation
where they left it, and the agent keeps the context ("e aquele violão de ontem?").
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

DEFAULT_DB = Path(
    os.getenv("CONVERSATIONS_DB", Path(__file__).resolve().parent.parent / "conversations.db")
)


class ConversationStore:
    def __init__(self, path: Path | str = DEFAULT_DB):
        self.path = str(path)
        with self._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    item TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )"""
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_session ON items(session_id)")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def load(self, session_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT item FROM items WHERE session_id = ? ORDER BY id", (session_id,)
            ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def append(self, session_id: str, items: list[dict]) -> None:
        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO items (session_id, item) VALUES (?, ?)",
                [(session_id, json.dumps(i, ensure_ascii=False)) for i in items],
            )

    def user_message_count(self, session_id: str) -> int:
        return sum(1 for i in self.load(session_id) if i.get("role") == "user")

    def user_messages_today(self) -> int:
        """Messages sent by all visitors today (UTC): a global cap protects the API budget."""
        with self._connect() as conn:
            (count,) = conn.execute(
                "SELECT COUNT(*) FROM items WHERE date(created_at) = date('now') "
                "AND json_extract(item, '$.role') = 'user'"
            ).fetchone()
        return count
