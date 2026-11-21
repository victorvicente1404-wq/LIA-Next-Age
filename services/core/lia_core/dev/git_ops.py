from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lia_core.dev.workspaces import WorkspaceRegistry

PROPOSAL_TTL_SECONDS = 300
MAX_OUTPUT = 12000
MAX_COMMIT_CONTENT_BYTES = 5_000_000
PROTECTED_BRANCHES = {"main", "master"}
SENSITIVE_PARTS = {".env", ".ssh", ".aws", ".azure", ".kube", ".docker"}
SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}


class GitOperationError(Exception):
    pass


class GitProposalNotFound(Exception):
    pass


@dataclass(frozen=True)
class GitProposal:
    id: str
    workspace_id: str
    action: str
    parameters: dict[str, Any]
    branch: str
    head: str
    fingerprint: str
    preview: str
    created_at: float


class GitOperationManager:
    """Typed Git operations. No shell, no arbitrary command input, and explicit approval."""

    def __init__(self, workspaces: WorkspaceRegistry) -> None:
        self._workspaces = workspaces
        self._proposals: dict[str, GitProposal] = {}
        self._git = shutil.which("git")

    def _run(
        self,
        root: Path,
        *arguments: str,
        check: bool = True,
        env_overrides: dict[str, str] | None = None,
        input_data: bytes | None = None,
    ) -> subprocess.CompletedProcess[str]:
        if not self._git:
            raise GitOperationError("Git não está instalado neste ambiente.")
        command_env = {
            "PATH": os.environ.get("PATH", str(Path(self._git).parent)),
            "HOME": str(Path.home()),
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_COUNT": "2",
            "GIT_CONFIG_KEY_0": "core.hooksPath",
            "GIT_CONFIG_VALUE_0": os.devnull,
            "GIT_CONFIG_KEY_1": "commit.gpgsign",
            "GIT_CONFIG_VALUE_1": "false",
        }
        if env_overrides:
            command_env.update(env_overrides)
        run_options: dict[str, Any] = {
            "check": False,
            "cwd": root,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "timeout": 20,
            "shell": False,
            "env": command_env,
        }
        if input_data is None:
            run_options.update({
                "stdin": subprocess.DEVNULL,
                "text": True,
                "encoding": "utf-8",
                "errors": "replace",
            })
        else:
            run_options["input"] = input_data
        try:
            result = subprocess.run([self._git, *arguments], **run_options)
        except subprocess.TimeoutExpired as exc:
            raise GitOperationError("A operação Git excedeu 20 segundos.") from exc
        raw_output = result.stdout
        output = (
            raw_output.decode("utf-8", errors="replace")[-MAX_OUTPUT:]
            if isinstance(raw_output, bytes)
            else raw_output[-MAX_OUTPUT:]
        )
        if check and result.returncode:
            raise GitOperationError(output.strip() or "O Git recusou a operação.")
        return subprocess.CompletedProcess(result.args, result.returncode, output)

    def _repo(self, workspace_id: str) -> Path:
        workspace = self._workspaces._workspace(workspace_id)
        root = workspace.root
        result = self._run(root, "rev-parse", "--show-toplevel")
        if Path(result.stdout.strip()).resolve() != root:
            raise GitOperationError("A raiz Git não corresponde ao workspace autorizado.")
        return root

    def _state(self, root: Path) -> tuple[str, str, str]:
        branch = self._run(root, "branch", "--show-current").stdout.strip()
        head = self._run(root, "rev-parse", "HEAD").stdout.strip()
        status = self._run(root, "status", "--porcelain=v1", "--untracked-files=all").stdout
        return branch, head, status

    @staticmethod
    def _fingerprint(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _stage_commit_snapshot(
        self, root: Path, paths: list[str], head: str
    ) -> tuple[str, str]:
        """Build an isolated index from exact file bytes, without running clean filters."""
        self._validate_paths(root, paths)
        total_size = 0
        with tempfile.TemporaryDirectory(prefix="lia-git-index-") as temporary:
            index_env = {"GIT_INDEX_FILE": str(Path(temporary) / "index")}
            self._run(root, "read-tree", head, env_overrides=index_env)
            digest = hashlib.sha256()
            for relative in sorted(paths):
                path = root / relative
                flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                try:
                    descriptor = os.open(path, flags)
                except OSError as exc:
                    raise GitOperationError(
                        "Um arquivo selecionado não pôde ser aberto com segurança."
                    ) from exc
                try:
                    file_stat = os.fstat(descriptor)
                    if not stat.S_ISREG(file_stat.st_mode):
                        raise GitOperationError(
                            "Somente arquivos regulares podem entrar em commits."
                        )
                    content = bytearray()
                    with os.fdopen(descriptor, "rb", closefd=False) as stream:
                        while chunk := stream.read(64 * 1024):
                            content.extend(chunk)
                    total_size += len(content)
                    if total_size > MAX_COMMIT_CONTENT_BYTES:
                        raise GitOperationError(
                            "O conteúdo selecionado excede o limite de 5 MB para revisão segura."
                        )
                    if len(content) != file_stat.st_size:
                        raise GitOperationError(
                            "Um arquivo mudou enquanto seu snapshot era calculado."
                        )
                    mode = "100755" if file_stat.st_mode & stat.S_IXUSR else "100644"
                    object_id = self._run(
                        root, "hash-object", "-w", "--no-filters", "--stdin",
                        input_data=bytes(content),
                    ).stdout.strip()
                    if not re.fullmatch(r"[0-9a-f]{40,64}", object_id):
                        raise GitOperationError("O Git não produziu um objeto de arquivo válido.")
                    self._run(
                        root, "update-index", "--add", "--cacheinfo",
                        mode, object_id, relative,
                        env_overrides=index_env,
                    )
                    digest.update(relative.encode("utf-8"))
                    digest.update(b"\0")
                    digest.update(mode.encode("ascii"))
                    digest.update(b"\0")
                    digest.update(object_id.encode("ascii"))
                    digest.update(b"\0")
                finally:
                    os.close(descriptor)
            tree = self._run(root, "write-tree", env_overrides=index_env).stdout.strip()
            if not re.fullmatch(r"[0-9a-f]{40,64}", tree):
                raise GitOperationError("O Git não produziu uma árvore válida para o commit.")
            return digest.hexdigest(), tree

    def _purge(self) -> None:
        now = time.monotonic()
        self._proposals = {
            key: item for key, item in self._proposals.items()
            if now - item.created_at <= PROPOSAL_TTL_SECONDS
        }

    @staticmethod
    def _validate_branch(name: str) -> str:
        normalized = name.strip()
        if not normalized or len(normalized) > 120:
            raise GitOperationError("Nome de branch inválido.")
        if normalized.lower() in PROTECTED_BRANCHES:
            raise GitOperationError("A Lia não pode criar ou substituir uma branch protegida.")
        if normalized.startswith(("-", "refs/")):
            raise GitOperationError("Nome de branch não permitido.")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", normalized):
            raise GitOperationError("Use letras, números, ponto, hífen, sublinhado ou barra no nome.")
        return normalized

    @staticmethod
    def _validate_paths(root: Path, paths: list[str]) -> list[str]:
        if not paths or len(paths) > 20:
            raise GitOperationError("Selecione entre 1 e 20 arquivos para o commit.")
        normalized: list[str] = []
        for raw in paths:
            path = Path(raw)
            if path.is_absolute() or not raw.strip() or path.as_posix() in {"", ".", ".."} or any(part in {"", ".", ".."} for part in path.parts):
                raise GitOperationError("Caminho de arquivo inválido.")
            if any(char in raw for char in "*?[]:") or "\\" in raw:
                raise GitOperationError("Use caminhos literais, sem padrões ou pathspecs Git.")
            if any(part.startswith("-") for part in path.parts):
                raise GitOperationError("Caminhos iniciados por hífen não são permitidos para commits.")
            if any(
                part.lower() in SENSITIVE_PARTS
                or (part.lower().startswith(".env") and part.lower() != ".env.example")
                for part in path.parts
            ):
                raise GitOperationError("Arquivos de ambiente ou diretórios sensíveis não podem entrar em commits.")
            if path.name.lower() in {"id_rsa", "id_ed25519", "credentials.json", "secrets.json"}:
                raise GitOperationError("Arquivo sensível bloqueado para commit.")
            if path.suffix.lower() in SENSITIVE_SUFFIXES:
                raise GitOperationError("Arquivo de chave/certificado bloqueado para commit.")
            absolute = root / path
            if (
                absolute.is_symlink()
                or not absolute.is_file()
                or not absolute.resolve().is_relative_to(root)
            ):
                raise GitOperationError(
                    "Somente arquivos regulares dentro do workspace podem entrar em commits."
                )
            normalized.append(path.as_posix())
        if len(set(normalized)) != len(normalized):
            raise GitOperationError("A lista contém caminhos duplicados.")
        return normalized

    def list_state(self, workspace_id: str) -> dict[str, Any]:
        root = self._repo(workspace_id)
        branch, head, status = self._state(root)
        branches = self._run(root, "for-each-ref", "--format=%(refname:short)", "refs/heads").stdout
        recent = self._run(
            root, "log", "-5", "--format=%H%x09%h%x09%s"
        ).stdout
        return {
            "branch": branch,
            "head": head,
            "dirty": bool(status.strip()),
            "clean": not bool(status.strip()),
            "status": status[-MAX_OUTPUT:],
            "branches": [item for item in branches.splitlines() if item],
            "recent_commits": [
                {"sha": parts[0], "short_sha": parts[1], "subject": parts[2]}
                for line in recent.splitlines()
                if len(parts := line.split("\t", 2)) == 3
            ],
        }

    def propose(
        self, workspace_id: str, action: str, parameters: dict[str, Any]
    ) -> dict[str, Any]:
        self._purge()
        root = self._repo(workspace_id)
        branch, head, status = self._state(root)
        if action in {"create_branch", "checkout", "commit", "revert_head"} and not branch:
            raise GitOperationError("O repositório está em estado detached HEAD; operação bloqueada.")
        if action in {"checkout", "revert_head", "create_branch"} and status.strip():
            raise GitOperationError(
                "Há alterações locais pendentes. Faça commit ou resolva-as antes de mudar de branch."
            )

        preview = ""
        fingerprint = self._fingerprint(status)
        normalized: dict[str, Any] = {}

        if action == "create_branch":
            name = self._validate_branch(str(parameters.get("branch", "")))
            exists = self._run(root, "show-ref", "--verify", "--quiet", f"refs/heads/{name}", check=False)
            if exists.returncode == 0:
                raise GitOperationError("Essa branch já existe.")
            self._run(root, "check-ref-format", "--branch", name)
            normalized = {"branch": name}
            preview = f"Criar branch local '{name}' a partir de {branch} ({head[:12]})."
        elif action == "checkout":
            name = self._validate_branch(str(parameters.get("branch", "")))
            if name == branch:
                raise GitOperationError("Essa branch já está ativa.")
            exists = self._run(root, "show-ref", "--verify", "--quiet", f"refs/heads/{name}", check=False)
            if exists.returncode != 0:
                raise GitOperationError("Apenas branches locais existentes podem ser selecionadas.")
            normalized = {"branch": name}
            preview = f"Trocar de '{branch}' para '{name}'. O workspace precisa estar limpo."
        elif action == "commit":
            if branch.lower() in PROTECTED_BRANCHES:
                raise GitOperationError("Commits na branch protegida estão bloqueados.")
            message = " ".join(str(parameters.get("message", "")).split())
            if not message or len(message) > 160:
                raise GitOperationError("A mensagem do commit deve ter entre 1 e 160 caracteres.")
            paths = self._validate_paths(root, list(parameters.get("paths", [])))
            for path in paths:
                tracked = self._run(root, "ls-files", "--error-unmatch", "--", path, check=False)
                if tracked.returncode != 0:
                    raise GitOperationError(f"'{path}' não é um arquivo já rastreado pelo Git.")
            diff_status = self._run(
                root, "diff", "--quiet", "HEAD", "--", *paths, check=False
            )
            if diff_status.returncode == 0:
                raise GitOperationError("Os arquivos selecionados não têm alterações para commit.")
            if diff_status.returncode != 1:
                raise GitOperationError("Não foi possível inspecionar os arquivos selecionados.")
            fingerprint, _ = self._stage_commit_snapshot(root, paths, head)
            normalized = {"message": message, "paths": paths}
            preview = (
                f"Commit na branch '{branch}'\nMensagem: {message}\n"
                f"Arquivos selecionados:\n" + "\n".join(f"- {path}" for path in paths)
                + "\n\nResumo:\n" + self._run(root, "diff", "--stat", "HEAD", "--", *paths).stdout
            )
        elif action == "revert_head":
            if branch.lower() in PROTECTED_BRANCHES:
                raise GitOperationError("Reverter commits na branch protegida está bloqueado.")
            parents = self._run(root, "rev-list", "--parents", "-n", "1", "HEAD").stdout.split()
            if len(parents) != 2:
                raise GitOperationError("Só é permitido reverter um commit comum, não merge nem commit raiz.")
            subject = self._run(root, "log", "-1", "--format=%s").stdout.strip()
            normalized = {"target": head}
            preview = (
                f"Criar um novo commit de reversão para {head[:12]} ({subject}) "
                f"na branch '{branch}'. O histórico não será apagado."
            )
        else:
            raise GitOperationError("Operação Git não permitida.")

        proposal_id = uuid.uuid4().hex
        proposal = GitProposal(
            id=proposal_id,
            workspace_id=workspace_id,
            action=action,
            parameters=normalized,
            branch=branch,
            head=head,
            fingerprint=fingerprint,
            preview=preview,
            created_at=time.monotonic(),
        )
        if len(self._proposals) >= 50:
            oldest = min(self._proposals, key=lambda key: self._proposals[key].created_at)
            self._proposals.pop(oldest, None)
        self._proposals[proposal_id] = proposal
        return {
            "proposal_id": proposal_id,
            "action": action,
            "preview": preview,
            "branch": branch,
            "expires_in_seconds": PROPOSAL_TTL_SECONDS,
        }

    def cancel(self, proposal_id: str) -> bool:
        self._purge()
        return self._proposals.pop(proposal_id, None) is not None

    def execute(self, proposal_id: str) -> dict[str, Any]:
        self._purge()
        proposal = self._proposals.pop(proposal_id, None)
        if proposal is None:
            raise GitProposalNotFound(proposal_id)
        root = self._repo(proposal.workspace_id)
        branch, head, status = self._state(root)
        if branch != proposal.branch or head != proposal.head:
            raise GitOperationError("O estado do Git mudou desde a revisão. Gere uma nova proposta.")
        if proposal.action in {"checkout", "create_branch", "revert_head"} and status.strip():
            raise GitOperationError("O workspace deixou de estar limpo. Operação cancelada.")
        if proposal.action == "commit":
            paths = proposal.parameters["paths"]
            current_fingerprint, tree = self._stage_commit_snapshot(
                root, paths, head
            )
            if current_fingerprint != proposal.fingerprint:
                raise GitOperationError("Os arquivos mudaram desde a revisão. Gere um novo commit proposto.")
            commit_sha = self._run(
                root, "commit-tree", tree, "-p", head,
                "-m", proposal.parameters["message"],
            ).stdout.strip()
            if not re.fullmatch(r"[0-9a-f]{40,64}", commit_sha):
                raise GitOperationError("O Git não produziu um commit válido.")
            result = self._run(
                root, "update-ref",
                f"refs/heads/{proposal.branch}", commit_sha, head,
            )
            # Synchronize only committed paths; unrelated staged changes remain untouched.
            self._run(root, "reset", "-q", "HEAD", "--", *paths)
        elif proposal.action == "create_branch":
            result = self._run(root, "switch", "-c", proposal.parameters["branch"])
        elif proposal.action == "checkout":
            result = self._run(root, "switch", proposal.parameters["branch"])
        else:
            if proposal.parameters["target"] != head:
                raise GitOperationError("O commit alvo mudou desde a revisão.")
            try:
                result = self._run(root, "revert", "--no-edit", "HEAD")
            except GitOperationError:
                self._run(root, "revert", "--abort", check=False)
                raise
        new_branch, new_head, new_status = self._state(root)
        return {
            "action": proposal.action,
            "success": True,
            "output": (
                f"Commit criado: {commit_sha}" if proposal.action == "commit"
                else result.stdout[-MAX_OUTPUT:]
            ),
            "branch": new_branch,
            "head": new_head,
            "clean": not bool(new_status.strip()),
        }
