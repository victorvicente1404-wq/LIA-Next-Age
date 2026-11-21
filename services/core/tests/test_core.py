from pathlib import Path

from fastapi.testclient import TestClient

from lia_core.config import Settings
from lia_core.main import create_app


class FakeLocalModel:
    async def complete(self, messages, temperature, max_tokens):
        assert messages[-1]["role"] == "user"
        return "Resposta local de teste."


def build_client(tmp_path: Path, inference=None) -> TestClient:
    settings = Settings(
        llm_base_url="http://127.0.0.1:8080/v1",
        llm_model="test-model",
        data_dir=tmp_path,
    )
    return TestClient(
        create_app(settings=settings, inference=inference, memory_path=tmp_path / "memory.sqlite3")
    )


def test_health_reports_local_runtime(tmp_path: Path):
    with build_client(tmp_path) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["inference"] == "local_endpoint_configured"


def test_chat_uses_injected_local_model(tmp_path: Path):
    with build_client(tmp_path, FakeLocalModel()) as client:
        response = client.post(
            "/api/v1/chat",
            json={"messages": [{"role": "user", "content": "Oi, Lia!"}]},
        )
    assert response.status_code == 200
    assert response.json() == {
        "content": "Resposta local de teste.",
        "engine": "llama.cpp",
        "external_traffic": False,
    }


def test_memory_is_persistent_and_searchable(tmp_path: Path):
    database = tmp_path / "memory.sqlite3"
    with build_client(tmp_path) as client:
        created = client.post(
            "/api/v1/memories",
            json={"kind": "preference", "key": "respostas", "content": "Prefiro respostas em português."},
        )
        assert created.status_code == 201
        memory_id = created.json()["id"]
        found = client.get("/api/v1/memories", params={"q": "português"})
        assert len(found.json()) == 1
        assert found.json()[0]["id"] == memory_id

    with build_client(tmp_path) as client:
        persisted = client.get("/api/v1/memories", params={"kind": "preference"})
        assert len(persisted.json()) == 1
        deleted = client.delete(f"/api/v1/memories/{memory_id}")
        assert deleted.status_code == 204
        missing = client.delete(f"/api/v1/memories/{memory_id}")
        assert missing.status_code == 404
