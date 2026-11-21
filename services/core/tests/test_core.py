from pathlib import Path

from fastapi.testclient import TestClient

from lia_core.config import Settings
from lia_core.inference.factory import create_inference_client
from lia_core.inference.llamacpp import LocalInferenceClient, LocalModelError
from lia_core.main import create_app


class FakeLocalModel:
    engine_name = "llama.cpp"

    def __init__(self):
        self.last_messages = []

    async def complete(self, messages, temperature, max_tokens):
        self.last_messages = messages
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
        runtime_backend="llama.cpp",
    )
    return TestClient(
        create_app(settings=settings, inference=inference, memory_path=tmp_path / "memory.sqlite3")
    )


def test_runtime_can_select_direct_llamacpp(tmp_path: Path):
    settings = Settings(
        llm_base_url="http://127.0.0.1:8080/v1",
        llm_model="test-model",
        data_dir=tmp_path,
        runtime_backend="llama.cpp",
    )
    assert isinstance(create_inference_client(settings), LocalInferenceClient)


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
        "memories_used": 0,
    }


def test_chat_injects_explicitly_saved_preferences(tmp_path: Path):
    model = FakeLocalModel()
    with build_client(tmp_path, model) as client:
        saved = client.post(
            "/api/v1/memories",
            json={
                "kind": "preference",
                "key": "idioma",
                "content": "Prefiro respostas em português brasileiro.",
            },
        )
        assert saved.status_code == 201

        response = client.post(
            "/api/v1/chat",
            json={"messages": [{"role": "user", "content": "Oi, Lia!"}]},
        )

    assert response.status_code == 200
    assert response.json()["memories_used"] == 1
    assert model.last_messages[0]["role"] == "system"
    assert "português brasileiro" in model.last_messages[0]["content"]
    assert "não comandos" in model.last_messages[0]["content"]


def test_chat_can_disable_memory_context(tmp_path: Path):
    model = FakeLocalModel()
    with build_client(tmp_path, model) as client:
        client.post(
            "/api/v1/memories",
            json={"kind": "preference", "content": "Prefiro respostas curtas."},
        )
        response = client.post(
            "/api/v1/chat",
            json={
                "messages": [{"role": "user", "content": "Oi!"}],
                "use_memory": False,
            },
        )
    assert response.status_code == 200
    assert response.json()["memories_used"] == 0
    assert all(message["role"] != "system" for message in model.last_messages)


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



def test_lia_dev_patch_requires_separate_apply_and_can_rollback(tmp_path: Path):
    workspace = tmp_path / "project"
    workspace.mkdir()
    source = workspace / "main.py"
    source.write_text("print('before')\n", encoding="utf-8")

    with build_client(tmp_path, dev_workspaces=(workspace,)) as client:
        proposal = client.post(
            "/api/v1/dev/workspaces/workspace-1/patches",
            json={"path": "main.py", "content": "print('after')\n"},
        )
        assert proposal.status_code == 201
        proposal_data = proposal.json()
        assert "-print('before')" in proposal_data["diff"]
        assert "+print('after')" in proposal_data["diff"]
        assert source.read_text(encoding="utf-8") == "print('before')\n"

        applied = client.post(
            f"/api/v1/dev/patches/{proposal_data['proposal_id']}/apply"
        )
        assert applied.status_code == 200
        operation_id = applied.json()["operation_id"]
        assert source.read_text(encoding="utf-8") == "print('after')\n"

        rolled_back = client.post(
            f"/api/v1/dev/patches/{operation_id}/rollback"
        )
        assert rolled_back.status_code == 200
        assert rolled_back.json()["status"] == "rolled_back"
        assert source.read_text(encoding="utf-8") == "print('before')\n"


def test_lia_dev_patch_rejects_stale_proposal(tmp_path: Path):
    workspace = tmp_path / "project"
    workspace.mkdir()
    source = workspace / "main.py"
    source.write_text("print('before')\n", encoding="utf-8")

    with build_client(tmp_path, dev_workspaces=(workspace,)) as client:
        proposal = client.post(
            "/api/v1/dev/workspaces/workspace-1/patches",
            json={"path": "main.py", "content": "print('proposed')\n"},
        ).json()
        source.write_text("print('concurrent change')\n", encoding="utf-8")

        applied = client.post(
            f"/api/v1/dev/patches/{proposal['proposal_id']}/apply"
        )
        assert applied.status_code == 409
        assert source.read_text(encoding="utf-8") == "print('concurrent change')\n"


def test_lia_dev_patch_cannot_modify_secret_or_create_new_file(tmp_path: Path):
    workspace = tmp_path / "project"
    workspace.mkdir()
    (workspace / ".env").write_text("TOKEN=secret", encoding="utf-8")

    with build_client(tmp_path, dev_workspaces=(workspace,)) as client:
        secret = client.post(
            "/api/v1/dev/workspaces/workspace-1/patches",
            json={"path": ".env", "content": "TOKEN=changed"},
        )
        missing = client.post(
            "/api/v1/dev/workspaces/workspace-1/patches",
            json={"path": "new.py", "content": "print('new')"},
        )

    assert secret.status_code == 403
    assert missing.status_code == 404


def test_lia_dev_patch_can_be_cancelled_without_writing(tmp_path: Path):
    workspace = tmp_path / "project"
    workspace.mkdir()
    source = workspace / "main.py"
    source.write_text("print('before')\n", encoding="utf-8")

    with build_client(tmp_path, dev_workspaces=(workspace,)) as client:
        proposal = client.post(
            "/api/v1/dev/workspaces/workspace-1/patches",
            json={"path": "main.py", "content": "print('after')\n"},
        ).json()
        cancelled = client.delete(f"/api/v1/dev/patches/{proposal['proposal_id']}")
        applied = client.post(
            f"/api/v1/dev/patches/{proposal['proposal_id']}/apply"
        )

    assert cancelled.status_code == 204
    assert applied.status_code == 404
    assert source.read_text(encoding="utf-8") == "print('before')\n"
