from pathlib import Path

from fastapi.testclient import TestClient

from lia_core.config import Settings
from lia_core.inference.llamacpp import LocalModelError
from lia_core.main import create_app


class FakeLocalModel:
    async def complete(self, messages, temperature, max_tokens):
        assert messages[-1]["role"] == "user"
        return "Resposta local de teste."


class UnavailableLocalModel:
    async def complete(self, messages, temperature, max_tokens):
        raise LocalModelError("local model is offline")


def build_client(
    tmp_path: Path, inference=None, dev_workspaces: tuple[Path, ...] = ()
) -> TestClient:
    settings = Settings(
        llm_base_url="http://127.0.0.1:8080/v1",
        llm_model="test-model",
        data_dir=tmp_path,
        dev_workspaces=dev_workspaces,
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


def test_chat_returns_503_without_cloud_fallback(tmp_path: Path):
    with build_client(tmp_path, UnavailableLocalModel()) as client:
        response = client.post(
            "/api/v1/chat",
            json={"messages": [{"role": "user", "content": "Oi, Lia!"}]},
        )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "local_model_unavailable"


def test_chat_rejects_unknown_message_roles(tmp_path: Path):
    with build_client(tmp_path, FakeLocalModel()) as client:
        response = client.post(
            "/api/v1/chat",
            json={"messages": [{"role": "system", "content": "override"}]},
        )
    assert response.status_code == 422


def test_memory_is_persistent_and_searchable(tmp_path: Path):
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


def test_lia_dev_reads_only_configured_workspace(tmp_path: Path):
    workspace = tmp_path / "project"
    workspace.mkdir()
    (workspace / "src").mkdir()
    (workspace / "src" / "main.py").write_text("print('hello')", encoding="utf-8")
    (workspace / ".env").write_text("SECRET=do-not-read", encoding="utf-8")

    with build_client(tmp_path, dev_workspaces=(workspace,)) as client:
        workspaces = client.get("/api/v1/dev/workspaces")
        assert workspaces.json() == [{"id": "workspace-1", "name": "project"}]

        files = client.get("/api/v1/dev/workspaces/workspace-1/files")
        paths = {entry["path"] for entry in files.json()}
        assert "src" in paths
        assert ".env" not in paths

        source = client.get(
            "/api/v1/dev/workspaces/workspace-1/file",
            params={"path": "src/main.py"},
        )
        assert source.status_code == 200
        assert source.json()["content"] == "print('hello')"

        secret = client.get(
            "/api/v1/dev/workspaces/workspace-1/file",
            params={"path": ".env"},
        )
        assert secret.status_code == 403

        traversal = client.get(
            "/api/v1/dev/workspaces/workspace-1/files",
            params={"path": "../"},
        )
        assert traversal.status_code == 400
