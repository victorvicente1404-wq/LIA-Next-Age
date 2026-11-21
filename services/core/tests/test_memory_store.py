from __future__ import annotations

import pytest

from lia_core.memory.store import MemoryStore, MemoryValidationError


def test_memory_store_normalizes_content_and_key(tmp_path):
    store = MemoryStore(tmp_path / "memory.sqlite3")

    saved = store.add("preference", "  Respostas em português.  ", " idioma ")

    assert saved["content"] == "Respostas em português."
    assert saved["key"] == "idioma"


@pytest.mark.parametrize(
    ("kind", "content"),
    [
        ("unknown", "conteúdo"),
        ("note", "   "),
        ("fact", "\\n\\t"),
    ],
)
def test_memory_store_rejects_invalid_entries(tmp_path, kind, content):
    store = MemoryStore(tmp_path / "memory.sqlite3")

    with pytest.raises(MemoryValidationError):
        store.add(kind, content)


def test_memory_context_respects_one_total_limit(tmp_path):
    store = MemoryStore(tmp_path / "memory.sqlite3")
    store.add("preference", "Prefiro português brasileiro.")
    store.add("preference", "Prefiro respostas objetivas.")
    store.add("knowledge", "O projeto usa SQLite para memória.")
    store.add("note", "O SQLite fica no dispositivo.")

    relevant = store.relevant("SQLite dispositivo", limit=3)

    assert len(relevant) == 3
    assert [item["kind"] for item in relevant[:2]] == ["preference", "preference"]
    assert any("SQLite" in item["content"] for item in relevant[2:])


def test_memory_context_zero_limit_returns_nothing(tmp_path):
    store = MemoryStore(tmp_path / "memory.sqlite3")
    store.add("preference", "Prefiro português.")

    assert store.relevant("português", limit=0) == []
