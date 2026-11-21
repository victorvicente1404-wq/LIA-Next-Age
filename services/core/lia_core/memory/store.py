from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MEMORY_KINDS = {"fact", "preference", "knowledge", "note"}


class MemoryValidationError(ValueError):
    """Raised when a memory entry is invalid."""


class MemoryStore:
    """SQLite store for explicit, user-approved memory entries."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._fts_enabled = False
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
            try:
                connection.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
                    USING fts5(kind, memory_key, content, tokenize='unicode61 remove_diacritics 2')
                    """
                )
                connection.executescript(
                    """
                    CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                        INSERT INTO memories_fts(rowid, kind, memory_key, content)
                        VALUES (new.id, new.kind, coalesce(new.memory_key, ''), new.content);
                    END;
                    CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                        DELETE FROM memories_fts WHERE rowid = old.id;
                    END;
                    """
                )
                connection.execute(
                    """
                    INSERT INTO memories_fts(rowid, kind, memory_key, content)
                    SELECT id, kind, coalesce(memory_key, ''), content
                    FROM memories
                    WHERE id NOT IN (SELECT rowid FROM memories_fts)
                    """
                )
                self._fts_enabled = True
            except sqlite3.OperationalError:
                self._fts_enabled = False

    def add(self, kind: str, content: str, key: str | None = None) -> dict[str, Any]:
        normalized_content = content.strip()
        normalized_key = key.strip() if key and key.strip() else None
        if kind not in MEMORY_KINDS:
            raise MemoryValidationError("Tipo de memória inválido.")
        if not normalized_content:
            raise MemoryValidationError("O conteúdo da memória não pode estar vazio.")
        if len(normalized_content) > 10_000:
            raise MemoryValidationError("O conteúdo da memória excede 10.000 caracteres.")
        if normalized_key is not None and len(normalized_key) > 200:
            raise MemoryValidationError("O identificador excede 200 caracteres.")

        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO memories (kind, memory_key, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (kind, normalized_key, normalized_content, created_at),
            )
            memory_id = int(cursor.lastrowid)
        return {
            "id": memory_id,
            "kind": kind,
            "key": normalized_key,
            "content": normalized_content,
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
        normalized_query = query.strip() if query else ""
        if normalized_query:
            clauses.append("(content LIKE ? OR memory_key LIKE ?)")
            pattern = f"%{normalized_query}%"
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

    def relevant(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Return persistent preferences and query matches within one total budget."""
        if limit <= 0:
            return []
        preferences = self.list(kind="preference", limit=limit)
        remaining = limit - len(preferences)
        matches: list[dict[str, Any]] = []
        terms = list(dict.fromkeys(re.findall(r"[\wÀ-ÿ]{3,}", query.lower())))[:10]

        if remaining > 0 and terms and self._fts_enabled:
            match_query = " OR ".join(f'"{term}"' for term in terms)
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT m.id, m.kind, m.memory_key, m.content, m.created_at
                    FROM memories_fts f
                    JOIN memories m ON m.id = f.rowid
                    WHERE memories_fts MATCH ?
                    ORDER BY bm25(memories_fts)
                    LIMIT ?
                    """,
                    (match_query, remaining + len(preferences)),
                ).fetchall()
            matches = [
                {
                    "id": row["id"],
                    "kind": row["kind"],
                    "key": row["memory_key"],
                    "content": row["content"],
                    "created_at": row["created_at"],
                }
                for row in rows
            ]
        elif remaining > 0 and terms:
            seen: set[int] = set()
            for term in terms:
                for item in self.list(query=term, limit=remaining + len(preferences)):
                    if item["id"] not in seen:
                        matches.append(item)
                        seen.add(item["id"])
                    if len(matches) >= remaining + len(preferences):
                        break
                if len(matches) >= remaining + len(preferences):
                    break

        combined: list[dict[str, Any]] = []
        seen_ids: set[int] = set()
        for item in preferences + matches:
            if item["id"] not in seen_ids:
                combined.append(item)
                seen_ids.add(item["id"])
            if len(combined) >= limit:
                break
        return combined

    def delete(self, memory_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            return cursor.rowcount > 0
