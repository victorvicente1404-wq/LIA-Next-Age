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
        create_app(settings=settings, inference=inference, memory_path=tmp_path / "memory.sqlite3"),
        client=("127.0.0.1", 12345),
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
        "agent": "simple",
        "specialist": "general",
        "tool_calls": 0,
        "agent_turns": 1,
        "plan": [],
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


def test_lia_dev_rollback_survives_core_restart(tmp_path: Path):
    workspace = tmp_path / "project"
    workspace.mkdir()
    source = workspace / "main.py"
    source.write_text("print('before')\n", encoding="utf-8")

    with build_client(tmp_path, dev_workspaces=(workspace,)) as first_client:
        proposal = first_client.post(
            "/api/v1/dev/workspaces/workspace-1/patches",
            json={"path": "main.py", "content": "print('after')\n"},
        ).json()
        applied = first_client.post(
            f"/api/v1/dev/patches/{proposal['proposal_id']}/apply"
        ).json()

    assert source.read_text(encoding="utf-8") == "print('after')\n"

    with build_client(tmp_path, dev_workspaces=(workspace,)) as restarted_client:
        available = restarted_client.get(
            "/api/v1/dev/rollbacks", params={"workspace_id": "workspace-1"}
        )
        assert [item["operation_id"] for item in available.json()] == [
            applied["operation_id"]
        ]
        rolled_back = restarted_client.post(
            f"/api/v1/dev/patches/{applied['operation_id']}/rollback"
        )

    assert rolled_back.status_code == 200
    assert source.read_text(encoding="utf-8") == "print('before')\n"


def test_lia_dev_lists_only_fixed_tasks_and_requires_approval(tmp_path: Path):
    import shutil
    import subprocess

    workspace = tmp_path / "project"
    workspace.mkdir()
    if not shutil.which("git"):
        return
    subprocess.run(["git", "init", "-q", str(workspace)], check=True)

    with build_client(tmp_path, dev_workspaces=(workspace,)) as client:
        tasks = client.get("/api/v1/dev/workspaces/workspace-1/tasks")
        assert tasks.status_code == 200
        task_ids = {item["task"] for item in tasks.json()}
        assert "git_status" in task_ids
        assert all("command" in item for item in tasks.json())

        proposal = client.post(
            "/api/v1/dev/workspaces/workspace-1/tasks",
            json={"task": "git_status"},
        )
        assert proposal.status_code == 201
        proposal_data = proposal.json()
        assert proposal_data["command"].endswith("status --short --branch")

        cancelled = client.delete(
            f"/api/v1/dev/tasks/{proposal_data['proposal_id']}"
        )
        execution = client.post(
            f"/api/v1/dev/tasks/{proposal_data['proposal_id']}/execute"
        )

    assert cancelled.status_code == 204
    assert execution.status_code == 404


def test_lia_dev_task_executes_only_after_approval_and_only_once(tmp_path: Path):
    import shutil
    import subprocess

    workspace = tmp_path / "project"
    workspace.mkdir()
    if not shutil.which("git"):
        return
    subprocess.run(["git", "init", "-q", str(workspace)], check=True)

    with build_client(tmp_path, dev_workspaces=(workspace,)) as client:
        rejected = client.post(
            "/api/v1/dev/workspaces/workspace-1/tasks",
            json={"task": "python -c"},
        )
        proposal = client.post(
            "/api/v1/dev/workspaces/workspace-1/tasks",
            json={"task": "git_status"},
        ).json()
        result = client.post(
            f"/api/v1/dev/tasks/{proposal['proposal_id']}/execute"
        )
        repeated = client.post(
            f"/api/v1/dev/tasks/{proposal['proposal_id']}/execute"
        )

    assert rejected.status_code == 400
    assert result.status_code == 200
    assert result.json()["success"] is True
    assert result.json()["return_code"] == 0
    assert repeated.status_code == 404


def test_conversation_history_persists_without_becoming_memory(tmp_path: Path):
    model = FakeLocalModel()
    with build_client(tmp_path, model) as client:
        created = client.post("/api/v1/conversations", json={"title": "Nova conversa"})
        assert created.status_code == 201
        conversation_id = created.json()["id"]

        response = client.post(
            "/api/v1/chat",
            json={
                "conversation_id": conversation_id,
                "messages": [{"role": "user", "content": "Vamos falar sobre robótica."}],
            },
        )
        assert response.status_code == 200
        assert response.json()["content"] == "Resposta local de teste."

        detail = client.get(f"/api/v1/conversations/{conversation_id}")
        assert detail.status_code == 200
        assert detail.json()["title"] == "Vamos falar sobre robótica."
        assert [item["role"] for item in detail.json()["messages"]] == [
            "user",
            "assistant",
        ]
        assert detail.json()["messages"][0]["content"] == "Vamos falar sobre robótica."
        assert client.get("/api/v1/memories").json() == []

    with build_client(tmp_path) as restarted_client:
        restored = restarted_client.get(f"/api/v1/conversations/{conversation_id}")
        assert restored.status_code == 200
        assert len(restored.json()["messages"]) == 2
        assert restarted_client.get("/api/v1/memories").json() == []


def test_conversation_endpoints_support_pagination_and_delete(tmp_path: Path):
    with build_client(tmp_path, FakeLocalModel()) as client:
        first = client.post("/api/v1/conversations", json={}).json()
        second = client.post(
            "/api/v1/conversations", json={"title": "Outra conversa"}
        ).json()
        assert len(client.get("/api/v1/conversations", params={"limit": 1}).json()) == 1
        assert client.get(f"/api/v1/conversations/{first['id']}?limit=1&offset=0").status_code == 200
        assert client.delete(f"/api/v1/conversations/{second['id']}").status_code == 204
        assert client.get(f"/api/v1/conversations/{second['id']}").status_code == 404
        assert client.delete(f"/api/v1/conversations/{second['id']}").status_code == 404


def test_legacy_chat_does_not_create_conversation_automatically(tmp_path: Path):
    with build_client(tmp_path, FakeLocalModel()) as client:
        response = client.post(
            "/api/v1/chat",
            json={"messages": [{"role": "user", "content": "Mensagem sem sessão."}]},
        )
        assert response.status_code == 200
        assert client.get("/api/v1/conversations").json() == []


def test_voice_status_reports_local_only_capabilities(tmp_path: Path):
    with build_client(tmp_path) as client:
        response = client.get("/api/v1/voice/status")

    assert response.status_code == 200
    assert response.json()["processing"] == "local_only"
    assert response.json()["transcription_configured"] is False
    assert response.json()["synthesis_configured"] is False


def test_voice_synthesis_endpoint_requires_local_piper_configuration(tmp_path: Path):
    with build_client(tmp_path) as client:
        response = client.post(
            "/api/v1/voice/speech",
            json={"text": "Olá, Lia!"},
        )

    assert response.status_code == 503

