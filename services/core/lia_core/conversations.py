from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ConversationNotFound(LookupError):
    """Raised when a conversation does not exist."""


class ConversationStore:
    """Persistent chat history, intentionally separate from long-term memories."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS conversation_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL CHECK(length(content) BETWEEN 1 AND 20000),
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_conversation_messages_order
                    ON conversation_messages(conversation_id, id);
                CREATE INDEX IF NOT EXISTS idx_conversations_updated
                    ON conversations(updated_at DESC);
                """
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _summary(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "title": row["title"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def create(self, title: str = "Nova conversa") -> dict[str, Any]:
        normalized = " ".join(title.split())[:72] or "Nova conversa"
        conversation_id = str(uuid.uuid4())
        now = self._now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (conversation_id, normalized, now, now),
            )
            row = connection.execute(
                "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
            ).fetchone()
        return self._summary(row)

    def list(self, limit: int = 30) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM conversations ORDER BY updated_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._summary(row) for row in rows]

    def get(self, conversation_id: str, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        with self._connect() as connection:
            conversation = connection.execute(
                "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
            ).fetchone()
            if conversation is None:
                raise ConversationNotFound(conversation_id)
            rows = connection.execute(
                """
                SELECT id, role, content, created_at
                FROM conversation_messages
                WHERE conversation_id = ?
                ORDER BY id ASC
                LIMIT ? OFFSET ?
                """,
                (conversation_id, limit, offset),
            ).fetchall()
        result = self._summary(conversation)
        result["messages"] = [dict(row) for row in rows]
        return result

    def append_turn(self, conversation_id: str, user_content: str, assistant_content: str) -> None:
        user_text = user_content.strip()
        assistant_text = assistant_content.strip()
        if not user_text or not assistant_text:
            raise ValueError("As mensagens da conversa não podem estar vazias.")
        if len(user_text) > 20000 or len(assistant_text) > 20000:
            raise ValueError("A mensagem excede 20.000 caracteres.")
        now = self._now()
        with self._connect() as connection:
            conversation = connection.execute(
                "SELECT title FROM conversations WHERE id = ?", (conversation_id,)
            ).fetchone()
            if conversation is None:
                raise ConversationNotFound(conversation_id)
            connection.executemany(
                """
                INSERT INTO conversation_messages (conversation_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (conversation_id, "user", user_text, now),
                    (conversation_id, "assistant", assistant_text, now),
                ],
            )
            title = conversation["title"]
            if title == "Nova conversa":
                title = " ".join(user_text.split())[:72] or "Nova conversa"
            connection.execute(
                "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                (title, now, conversation_id),
            )

    def delete(self, conversation_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM conversations WHERE id = ?", (conversation_id,)
            )
            return cursor.rowcount > 0
