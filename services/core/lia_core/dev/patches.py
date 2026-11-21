from __future__ import annotations

import difflib
import hashlib
import os
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from lia_core.dev.workspaces import (
    MAX_FILE_BYTES,
    SensitiveWorkspaceFile,
    UnsupportedTextFile,
    UnsafeWorkspacePath,
    WorkspaceFileTooLarge,
    WorkspaceItemNotFound,
    WorkspaceRegistry,
)


class PatchNotFound(Exception):
    pass


class PatchConflict(Exception):
    pass


@dataclass(frozen=True)
class PatchProposal:
    id: str
    workspace_id: str
    path: str
    original_sha256: str
    proposed_content: str
    diff: str
    created_at: str


@dataclass(frozen=True)
class AppliedPatch:
    id: str
    workspace_id: str
    path: str
    backup_path: Path
    applied_sha256: str


class PatchManager:
    """Two-step, in-memory patch approval with disk backups for rollback."""

    def __init__(self, workspaces: WorkspaceRegistry, backup_dir: Path) -> None:
        self._workspaces = workspaces
        self._backup_dir = backup_dir
        self._proposals: dict[str, PatchProposal] = {}
        self._applied: dict[str, AppliedPatch] = {}

    def propose(self, workspace_id: str, relative_path: str, content: str) -> dict[str, object]:
        if len(content.encode("utf-8")) > MAX_FILE_BYTES:
            raise WorkspaceFileTooLarge(relative_path)
        current = self._workspaces.read_file(workspace_id, relative_path)
        original = current["content"]
        proposal_id = uuid.uuid4().hex
        diff = "".join(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                content.splitlines(keepends=True),
                fromfile=f"a/{current['path']}",
                tofile=f"b/{current['path']}",
            )
        )
        proposal = PatchProposal(
            id=proposal_id,
            workspace_id=workspace_id,
            path=current["path"],
            original_sha256=hashlib.sha256(original.encode("utf-8")).hexdigest(),
            proposed_content=content,
            diff=diff,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._proposals[proposal_id] = proposal
        return {
            "proposal_id": proposal.id,
            "workspace_id": proposal.workspace_id,
            "path": proposal.path,
            "original_sha256": proposal.original_sha256,
            "diff": proposal.diff,
            "created_at": proposal.created_at,
            "status": "awaiting_approval",
        }

    def apply(self, proposal_id: str) -> dict[str, str]:
        proposal = self._proposals.get(proposal_id)
        if proposal is None:
            raise PatchNotFound(proposal_id)
        backup_path, applied_sha = self._replace(
            proposal.workspace_id,
            proposal.path,
            proposal.original_sha256,
            proposal.proposed_content,
        )
        operation_id = uuid.uuid4().hex
        self._applied[operation_id] = AppliedPatch(
            id=operation_id,
            workspace_id=proposal.workspace_id,
            path=proposal.path,
            backup_path=backup_path,
            applied_sha256=applied_sha,
        )
        del self._proposals[proposal_id]
        return {
            "operation_id": operation_id,
            "path": proposal.path,
            "applied_sha256": applied_sha,
            "status": "applied",
        }

    def rollback(self, operation_id: str) -> dict[str, str]:
        operation = self._applied.get(operation_id)
        if operation is None:
            raise PatchNotFound(operation_id)
        try:
            original_content = operation.backup_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise PatchNotFound(operation_id) from exc
        backup_path, restored_sha = self._replace(
            operation.workspace_id,
            operation.path,
            operation.applied_sha256,
            original_content,
        )
        self._applied.pop(operation_id, None)
        return {
            "rollback_id": operation_id,
            "path": operation.path,
            "restored_sha256": restored_sha,
            "status": "rolled_back",
            "previous_version_backup": str(backup_path),
        }

    def _replace(
        self, workspace_id: str, relative_path: str, expected_sha256: str, content: str
    ) -> tuple[Path, str]:
        workspace = self._workspaces._workspace(workspace_id)
        supplied = Path(relative_path)
        if supplied.is_absolute() or ".." in supplied.parts:
            raise UnsafeWorkspacePath(relative_path)
        cursor = workspace.root
        for part in supplied.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise UnsafeWorkspacePath(relative_path)
        target = self._workspaces._resolve_inside(workspace.root, relative_path)
        if not target.is_file():
            raise WorkspaceItemNotFound(relative_path)
        if self._workspaces._is_sensitive(target):
            raise SensitiveWorkspaceFile(relative_path)
        current_bytes = target.read_bytes()
        if len(current_bytes) > MAX_FILE_BYTES:
            raise WorkspaceFileTooLarge(relative_path)
        try:
            current_text = current_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise UnsupportedTextFile(relative_path) from exc
        current_sha = hashlib.sha256(current_text.encode("utf-8")).hexdigest()
        if current_sha != expected_sha256:
            raise PatchConflict(relative_path)

        new_bytes = content.encode("utf-8")
        if len(new_bytes) > MAX_FILE_BYTES:
            raise WorkspaceFileTooLarge(relative_path)
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = self._backup_dir / f"{uuid.uuid4().hex}.bak"
        backup_path.write_bytes(current_bytes)

        temp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=target.parent, prefix=".lia-patch-", delete=False
            ) as temporary:
                temp_name = temporary.name
                temporary.write(new_bytes)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.chmod(temp_name, target.stat().st_mode)
            os.replace(temp_name, target)
        except Exception:
            if temp_name is not None:
                try:
                    os.unlink(temp_name)
                except OSError:
                    pass
            try:
                backup_path.unlink()
            except OSError:
                pass
            raise

        return backup_path, hashlib.sha256(new_bytes).hexdigest()
