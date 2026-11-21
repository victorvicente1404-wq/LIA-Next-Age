from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


IGNORED_NAMES = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".next",
}
SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}
SENSITIVE_NAMES = {
    ".env",
    "id_rsa",
    "id_ed25519",
    "credentials.json",
    "secrets.json",
}
MAX_FILE_BYTES = 256 * 1024


class WorkspaceError(Exception):
    """Base error for workspace access."""


class WorkspaceNotFound(WorkspaceError):
    pass


class UnsafeWorkspacePath(WorkspaceError):
    pass


class WorkspaceItemNotFound(WorkspaceError):
    pass


class SensitiveWorkspaceFile(WorkspaceError):
    pass


class WorkspaceFileTooLarge(WorkspaceError):
    pass


class UnsupportedTextFile(WorkspaceError):
    pass


@dataclass(frozen=True)
class Workspace:
    id: str
    name: str
    root: Path


class WorkspaceRegistry:
    """Read-only access to directories explicitly added to Lia's allowlist."""

    def __init__(self, roots: Iterable[Path]) -> None:
        workspaces: list[Workspace] = []
        for index, configured_root in enumerate(roots, start=1):
            try:
                root = Path(configured_root).expanduser().resolve(strict=True)
            except OSError:
                continue
            if root.is_dir():
                workspaces.append(
                    Workspace(id=f"workspace-{index}", name=root.name or str(root), root=root)
                )
        self._workspaces = {workspace.id: workspace for workspace in workspaces}

    def list_workspaces(self) -> list[dict[str, str]]:
        return [
            {"id": item.id, "name": item.name}
            for item in self._workspaces.values()
        ]

    def _workspace(self, workspace_id: str) -> Workspace:
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            raise WorkspaceNotFound(workspace_id)
        return workspace

    @staticmethod
    def _resolve_inside(root: Path, relative_path: str) -> Path:
        supplied = Path(relative_path)
        if supplied.is_absolute():
            raise UnsafeWorkspacePath(relative_path)
        try:
            resolved = (root / supplied).resolve(strict=True)
        except OSError as exc:
            raise WorkspaceItemNotFound(relative_path) from exc
        if not resolved.is_relative_to(root):
            raise UnsafeWorkspacePath(relative_path)
        return resolved

    @staticmethod
    def _is_sensitive(path: Path) -> bool:
        name = path.name.lower()
        if name in SENSITIVE_NAMES:
            return True
        if name.startswith(".env.") and name != ".env.example":
            return True
        return path.suffix.lower() in SENSITIVE_SUFFIXES

    def list_files(self, workspace_id: str, relative_path: str = ".") -> list[dict[str, Any]]:
        workspace = self._workspace(workspace_id)
        directory = self._resolve_inside(workspace.root, relative_path)
        if not directory.is_dir():
            raise WorkspaceItemNotFound(relative_path)

        entries: list[dict[str, Any]] = []
        for item in sorted(directory.iterdir(), key=lambda value: (not value.is_dir(), value.name.lower())):
            if item.is_symlink() or item.name in IGNORED_NAMES or self._is_sensitive(item):
                continue
            try:
                resolved = item.resolve(strict=True)
                if not resolved.is_relative_to(workspace.root):
                    continue
                stat = item.stat()
            except OSError:
                continue
            entries.append(
                {
                    "name": item.name,
                    "path": item.relative_to(workspace.root).as_posix(),
                    "kind": "directory" if item.is_dir() else "file",
                    "size": None if item.is_dir() else stat.st_size,
                }
            )
            if len(entries) >= 200:
                break
        return entries

    def read_file(self, workspace_id: str, relative_path: str) -> dict[str, Any]:
        workspace = self._workspace(workspace_id)
        file_path = self._resolve_inside(workspace.root, relative_path)
        if not file_path.is_file():
            raise WorkspaceItemNotFound(relative_path)
        if self._is_sensitive(file_path):
            raise SensitiveWorkspaceFile(relative_path)
        size = file_path.stat().st_size
        if size > MAX_FILE_BYTES:
            raise WorkspaceFileTooLarge(relative_path)
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise UnsupportedTextFile(relative_path) from exc
        return {
            "path": file_path.relative_to(workspace.root).as_posix(),
            "content": content,
            "size": size,
        }
