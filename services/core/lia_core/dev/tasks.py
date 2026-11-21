from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import ClassVar

from lia_core.dev.workspaces import WorkspaceRegistry

MAX_OUTPUT_CHARS = 12_000
COMMAND_TIMEOUT_SECONDS = 120
PROPOSAL_TTL_MINUTES = 5


class TaskNotAvailable(Exception):
    pass


class TaskProposalNotFound(Exception):
    pass


@dataclass(frozen=True)
class TaskProposal:
    id: str
    workspace_id: str
    task: str
    command: tuple[str, ...]
    cwd: Path
    created_at: str


class TaskRunner:
    """Runs only fixed, reviewed development tasks after a separate approval."""

    TASK_LABELS: ClassVar[dict[str, str]] = {
        "git_status": "Git: status",
        "git_diff_stat": "Git: resumo do diff",
        "python_tests": "Python: testes pytest",
        "python_lint": "Python: Ruff",
        "web_build": "Web: build de produção",
    }

    def __init__(self, workspaces: WorkspaceRegistry) -> None:
        self._workspaces = workspaces
        self._proposals: dict[str, TaskProposal] = {}

    def _purge_expired(self) -> None:
        now = datetime.now(timezone.utc)
        for proposal_id, proposal in list(self._proposals.items()):
            created = datetime.fromisoformat(proposal.created_at)
            if now - created > timedelta(minutes=PROPOSAL_TTL_MINUTES):
                self._proposals.pop(proposal_id, None)

    def _command_for(self, task: str, root: Path) -> tuple[str, ...]:
        if task == "git_status":
            if not (root / ".git").exists():
                raise TaskNotAvailable("Este workspace não contém um repositório Git.")
            executable = shutil.which("git")
            if not executable:
                raise TaskNotAvailable("Git não está instalado neste ambiente.")
            return (executable, "status", "--short", "--branch")
        if task == "git_diff_stat":
            if not (root / ".git").exists():
                raise TaskNotAvailable("Este workspace não contém um repositório Git.")
            executable = shutil.which("git")
            if not executable:
                raise TaskNotAvailable("Git não está instalado neste ambiente.")
            return (executable, "diff", "--stat", "--")
        if task == "python_tests":
            if not (root / "pyproject.toml").is_file() and not (root / "pytest.ini").is_file():
                raise TaskNotAvailable("Não encontrei pyproject.toml nem pytest.ini na raiz.")
            return (sys.executable, "-m", "pytest", "-q")
        if task == "python_lint":
            if not (root / "pyproject.toml").is_file():
                raise TaskNotAvailable("Não encontrei pyproject.toml na raiz.")
            return (sys.executable, "-m", "ruff", "check", ".")
        if task == "web_build":
            package = root / "package.json"
            lock = root / "package-lock.json"
            if not package.is_file() or not lock.is_file():
                raise TaskNotAvailable("Build web exige package.json e package-lock.json na raiz.")
            executable = shutil.which("npm")
            if not executable:
                raise TaskNotAvailable("npm não está instalado neste ambiente.")
            return (executable, "run", "build")
        raise TaskNotAvailable("Tarefa não permitida.")

    def list_tasks(self, workspace_id: str) -> list[dict[str, str]]:
        workspace = self._workspaces._workspace(workspace_id)
        result = []
        for task, label in self.TASK_LABELS.items():
            try:
                command = self._command_for(task, workspace.root)
            except TaskNotAvailable:
                continue
            result.append({
                "task": task,
                "label": label,
                "command": " ".join(command),
            })
        return result

    def propose(self, workspace_id: str, task: str) -> dict[str, str]:
        self._purge_expired()
        workspace = self._workspaces._workspace(workspace_id)
        command = self._command_for(task, workspace.root)
        proposal_id = uuid.uuid4().hex
        created_at = datetime.now(timezone.utc).isoformat()
        proposal = TaskProposal(
            id=proposal_id,
            workspace_id=workspace_id,
            task=task,
            command=command,
            cwd=workspace.root,
            created_at=created_at,
        )
        if len(self._proposals) >= 50:
            oldest_id = min(self._proposals, key=lambda key: self._proposals[key].created_at)
            self._proposals.pop(oldest_id, None)
        self._proposals[proposal_id] = proposal
        return {
            "proposal_id": proposal_id,
            "workspace_id": workspace_id,
            "task": task,
            "label": self.TASK_LABELS[task],
            "command": " ".join(command),
            "cwd": str(workspace.root),
            "created_at": created_at,
            "expires_in_seconds": str(PROPOSAL_TTL_MINUTES * 60),
        }

    def cancel(self, proposal_id: str) -> bool:
        self._purge_expired()
        return self._proposals.pop(proposal_id, None) is not None

    def execute(self, proposal_id: str) -> dict[str, object]:
        self._purge_expired()
        proposal = self._proposals.pop(proposal_id, None)
        if proposal is None:
            raise TaskProposalNotFound(proposal_id)
        workspace = self._workspaces._workspace(proposal.workspace_id)
        if workspace.root != proposal.cwd or not proposal.cwd.is_dir():
            raise TaskNotAvailable("O workspace mudou desde a proposta.")
        environment = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(Path.home()),
            "CI": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
        }
        started = time.monotonic()
        timed_out = False
        try:
            completed = subprocess.run(
                proposal.command,
                cwd=proposal.cwd,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=COMMAND_TIMEOUT_SECONDS,
                check=False,
                shell=False,
            )
            output = completed.stdout
            return_code = completed.returncode
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            captured = exc.stdout or b""
            output = (
                captured.decode("utf-8", errors="replace")
                if isinstance(captured, bytes)
                else captured
            )
            return_code = None
        duration_ms = round((time.monotonic() - started) * 1000)
        truncated = len(output) > MAX_OUTPUT_CHARS
        if truncated:
            output = output[:MAX_OUTPUT_CHARS] + "\n… saída truncada pelo limite da Lia."
        return {
            "task": proposal.task,
            "label": self.TASK_LABELS[proposal.task],
            "command": " ".join(proposal.command),
            "cwd": str(proposal.cwd),
            "return_code": return_code,
            "success": return_code == 0 and not timed_out,
            "timed_out": timed_out,
            "duration_ms": duration_ms,
            "output": output,
            "output_truncated": truncated,
        }
