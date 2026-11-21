from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class MemoryStore:
    """Small SQLite store for explicit, user-approved memory entries."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL CHECK(kind IN ('fact', 'preference', 'knowledge', 'note')),
                    memory_key TEXT,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_kind ON memories(kind)"
            )

    def add(self, kind: str, content: str, key: str | None = None) -> dict[str, Any]:
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO memories (kind, memory_key, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (kind, key, content.strip(), created_at),
            )
            memory_id = int(cursor.lastrowid)
        return {
            "id": memory_id,
            "kind": kind,
            "key": key,
            "content": content.strip(),
            "created_at": created_at,
        }

    def list(
        self, query: str | None = None, kind: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        parameters: list[Any] = []
        if kind:
            clauses.append("kind = ?")
            parameters.append(kind)
        if query:
            clauses.append("(content LIKE ? OR memory_key LIKE ?)")
            pattern = f"%{query.strip()}%"
            parameters.extend((pattern, pattern))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT id, kind, memory_key, content, created_at
                FROM memories {where}
                ORDER BY id DESC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        return [
            {
                "id": row["id"],
                "kind": row["kind"],
                "key": row["memory_key"],
                "content": row["content"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def delete(self, memory_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            return cursor.rowcount > 0
