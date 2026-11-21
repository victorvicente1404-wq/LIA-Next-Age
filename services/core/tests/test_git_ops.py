from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from lia_core.config import Settings
from lia_core.main import create_app


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def make_repo(root: Path) -> None:
    root.mkdir()
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "Lia Test")
    git(root, "config", "user.email", "lia-test@example.invalid")
    (root / "README.md").write_text("versão inicial\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-m", "initial")


def client_for(tmp_path: Path, workspace: Path) -> TestClient:
    settings = Settings(
        llm_base_url="http://127.0.0.1:8080/v1",
        llm_model="test-model",
        data_dir=tmp_path / "data",
        dev_workspaces=(workspace,),
        runtime_backend="llama.cpp",
    )
    return TestClient(create_app(settings=settings), client=("127.0.0.1", 12345))


def test_git_branch_commit_and_revert_require_review_and_approval(tmp_path: Path):
    workspace = tmp_path / "project"
    make_repo(workspace)

    with client_for(tmp_path, workspace) as client:
        state = client.get("/api/v1/dev/workspaces/workspace-1/git")
        assert state.status_code == 200
        assert state.json()["branch"] == "main"
        assert state.json()["clean"] is True

        branch_proposal = client.post(
            "/api/v1/dev/workspaces/workspace-1/git/proposals",
            json={"action": "create_branch", "branch": "feature/lia-dev"},
        )
        assert branch_proposal.status_code == 201
        assert git(workspace, "branch", "--show-current") == "main"
        branch_result = client.post(
            f"/api/v1/dev/git/proposals/{branch_proposal.json()['proposal_id']}/execute"
        )
        assert branch_result.status_code == 200
        assert branch_result.json()["branch"] == "feature/lia-dev"

        (workspace / "README.md").write_text("versão alterada\n", encoding="utf-8")
        commit_proposal = client.post(
            "/api/v1/dev/workspaces/workspace-1/git/proposals",
            json={
                "action": "commit",
                "message": "Atualiza README",
                "paths": ["README.md"],
            },
        )
        assert commit_proposal.status_code == 201
        assert "README.md" in commit_proposal.json()["preview"]
        assert git(workspace, "rev-list", "--count", "HEAD") == "1"
        commit_result = client.post(
            f"/api/v1/dev/git/proposals/{commit_proposal.json()['proposal_id']}/execute"
        )
        assert commit_result.status_code == 200
        assert commit_result.json()["clean"] is True
        assert git(workspace, "rev-list", "--count", "HEAD") == "2"

        revert_proposal = client.post(
            "/api/v1/dev/workspaces/workspace-1/git/proposals",
            json={"action": "revert_head"},
        )
        assert revert_proposal.status_code == 201
        revert_result = client.post(
            f"/api/v1/dev/git/proposals/{revert_proposal.json()['proposal_id']}/execute"
        )
        assert revert_result.status_code == 200
        assert git(workspace, "rev-list", "--count", "HEAD") == "3"
        assert (workspace / "README.md").read_text(encoding="utf-8") == "versão inicial\n"


def test_git_operations_protect_main_and_reject_stale_proposals(tmp_path: Path):
    workspace = tmp_path / "project"
    make_repo(workspace)

    with client_for(tmp_path, workspace) as client:
        protected = client.post(
            "/api/v1/dev/workspaces/workspace-1/git/proposals",
            json={"action": "commit", "message": "Não permitido", "paths": ["README.md"]},
        )
        assert protected.status_code == 400
        assert "branch protegida" in protected.json()["detail"]

        proposal = client.post(
            "/api/v1/dev/workspaces/workspace-1/git/proposals",
            json={"action": "create_branch", "branch": "feature/stale"},
        )
        assert proposal.status_code == 201
        (workspace / "README.md").write_text("mudança concorrente\n", encoding="utf-8")
        result = client.post(
            f"/api/v1/dev/git/proposals/{proposal.json()['proposal_id']}/execute"
        )
        assert result.status_code == 409
        assert git(workspace, "branch", "--show-current") == "main"


def test_git_commit_rejects_sensitive_paths_and_globs(tmp_path: Path):
    workspace = tmp_path / "project"
    make_repo(workspace)
    (workspace / "app.py").write_text("print('ok')\n", encoding="utf-8")
    git(workspace, "add", "app.py")
    git(workspace, "commit", "-m", "add app")
    git(workspace, "switch", "-c", "feature/safe")
    (workspace / "app.py").write_text("print('changed')\n", encoding="utf-8")
    (workspace / ".env").write_text("TOKEN=secret\n", encoding="utf-8")

    with client_for(tmp_path, workspace) as client:
        secret = client.post(
            "/api/v1/dev/workspaces/workspace-1/git/proposals",
            json={"action": "commit", "message": "bad", "paths": [".env"]},
        )
        glob = client.post(
            "/api/v1/dev/workspaces/workspace-1/git/proposals",
            json={"action": "commit", "message": "bad", "paths": ["*.py"]},
        )
        backslash = client.post(
            "/api/v1/dev/workspaces/workspace-1/git/proposals",
            json={"action": "commit", "message": "bad", "paths": [r"..\escape"]},
        )
        unsafe_checkout = client.post(
            "/api/v1/dev/workspaces/workspace-1/git/proposals",
            json={"action": "checkout", "branch": "../../main"},
        )
    assert secret.status_code == 400
    assert glob.status_code == 400
    assert backslash.status_code == 400
    assert unsafe_checkout.status_code == 400


def test_git_commit_rejects_directory_path_to_prevent_sensitive_file_bypass(tmp_path: Path):
    workspace = tmp_path / "project"
    make_repo(workspace)
    source_dir = workspace / "src"
    source_dir.mkdir()
    (source_dir / "app.py").write_text("print('safe')\n", encoding="utf-8")
    (source_dir / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    git(workspace, "add", "src/app.py", "src/.env")
    git(workspace, "commit", "-m", "add source files")
    git(workspace, "switch", "-c", "feature/directory-test")
    (source_dir / "app.py").write_text("print('changed')\n", encoding="utf-8")
    (source_dir / ".env").write_text("TOKEN=changed-secret\n", encoding="utf-8")

    with client_for(tmp_path, workspace) as client:
        proposal = client.post(
            "/api/v1/dev/workspaces/workspace-1/git/proposals",
            json={"action": "commit", "message": "unsafe directory commit", "paths": ["src"]},
        )

    assert proposal.status_code == 400
    assert "arquivos regulares" in proposal.json()["detail"]
    assert "src/.env" in git(workspace, "status", "--short")


def test_git_commit_detects_changes_before_truncated_diff_prefix(tmp_path: Path):
    workspace = tmp_path / "project"
    make_repo(workspace)
    app_file = workspace / "app.py"
    app_file.write_text("a" * 20_000 + "\n", encoding="utf-8")
    git(workspace, "add", "app.py")
    git(workspace, "commit", "-m", "add large source file")
    git(workspace, "switch", "-c", "feature/large-diff")
    app_file.write_text("b" + "a" * 20_000 + "\n", encoding="utf-8")

    with client_for(tmp_path, workspace) as client:
        proposal = client.post(
            "/api/v1/dev/workspaces/workspace-1/git/proposals",
            json={"action": "commit", "message": "review large diff", "paths": ["app.py"]},
        )
        assert proposal.status_code == 201
        proposal_id = proposal.json()["proposal_id"]
        reviewed_head = git(workspace, "rev-parse", "HEAD")
        app_file.write_text("c" + "a" * 20_000 + "\n", encoding="utf-8")
        result = client.post(f"/api/v1/dev/git/proposals/{proposal_id}/execute")

    assert result.status_code == 409
    assert git(workspace, "rev-parse", "HEAD") == reviewed_head
    assert "app.py" in git(workspace, "status", "--short")



def test_git_commit_uses_approved_snapshot_if_worktree_changes_after_blob_write(
    tmp_path: Path, monkeypatch
):
    from lia_core.dev.git_ops import GitOperationManager

    workspace = tmp_path / "project"
    make_repo(workspace)
    app_file = workspace / "README.md"
    app_file.write_text("conteúdo aprovado\n", encoding="utf-8")
    git(workspace, "switch", "-c", "feature/snapshot-race")
    with client_for(tmp_path, workspace) as client:
        proposal = client.post(
            "/api/v1/dev/workspaces/workspace-1/git/proposals",
            json={
                "action": "commit",
                "message": "commit reviewed snapshot",
                "paths": ["README.md"],
            },
        )
        assert proposal.status_code == 201
        proposal_id = proposal.json()["proposal_id"]
        original_run = GitOperationManager._run
        changed = False

        def mutate_after_blob_write(self, root, *arguments, **kwargs):
            nonlocal changed
            result = original_run(self, root, *arguments, **kwargs)
            if arguments and arguments[0] == "hash-object" and kwargs.get("input_data") and not changed:
                changed = True
                app_file.write_text("conteúdo não aprovado\n", encoding="utf-8")
            return result

        monkeypatch.setattr(GitOperationManager, "_run", mutate_after_blob_write)
        executed = client.post(f"/api/v1/dev/git/proposals/{proposal_id}/execute")

    assert executed.status_code == 200
    assert changed is True
    assert git(workspace, "show", "HEAD:README.md") == "conteúdo aprovado"
    assert app_file.read_text(encoding="utf-8") == "conteúdo não aprovado\n"
    assert "README.md" in git(workspace, "status", "--short")


def test_git_commit_rejects_environment_variants_but_allows_example_template(tmp_path: Path):
    workspace = tmp_path / "project"
    make_repo(workspace)
    names = [".env.local", ".env.production", ".envrc", ".env.example"]
    for name in names:
        (workspace / name).write_text("SETTING=value\n", encoding="utf-8")
    git(workspace, "add", *names)
    git(workspace, "commit", "-m", "add environment examples")
    git(workspace, "switch", "-c", "feature/env-protection")
    for name in names:
        (workspace / name).write_text("SETTING=changed\n", encoding="utf-8")

    with client_for(tmp_path, workspace) as client:
        rejected = [
            client.post(
                "/api/v1/dev/workspaces/workspace-1/git/proposals",
                json={"action": "commit", "message": "must block", "paths": [name]},
            )
            for name in names[:-1]
        ]
        example = client.post(
            "/api/v1/dev/workspaces/workspace-1/git/proposals",
            json={
                "action": "commit",
                "message": "update safe template",
                "paths": [".env.example"],
            },
        )

    assert all(response.status_code == 400 for response in rejected)
    assert example.status_code == 201
