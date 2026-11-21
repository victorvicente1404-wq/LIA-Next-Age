from __future__ import annotations

from pathlib import Path
from typing import Literal, Protocol

from fastapi import FastAPI, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field

from lia_core.config import Settings
from lia_core.dev.workspaces import (
    SensitiveWorkspaceFile,
    UnsafeWorkspacePath,
    UnsupportedTextFile,
    WorkspaceFileTooLarge,
    WorkspaceItemNotFound,
    WorkspaceNotFound,
    WorkspaceRegistry,
)
from lia_core.inference.factory import create_inference_client
from lia_core.inference.llamacpp import LocalModelError
from lia_core.memory.store import MemoryStore


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "lia-core"
    inference: str
    memory: str = "sqlite"


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=40)
    system: str | None = Field(default=None, max_length=12000)
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int = Field(default=512, ge=1, le=4096)


class ChatResponse(BaseModel):
    content: str
    engine: str = "llama.cpp"
    external_traffic: bool = False


class ChatEngine(Protocol):
    async def complete(
        self, messages: list[dict[str, str]], temperature: float, max_tokens: int
    ) -> str: ...


class MemoryCreate(BaseModel):
    kind: str = Field(pattern="^(fact|preference|knowledge|note)$")
    content: str = Field(min_length=1, max_length=10000)
    key: str | None = Field(default=None, max_length=200)


class MemoryItem(BaseModel):
    id: int
    kind: str
    key: str | None
    content: str
    created_at: str


class WorkspaceSummary(BaseModel):
    id: str
    name: str


class WorkspaceFileEntry(BaseModel):
    name: str
    path: str
    kind: Literal["file", "directory"]
    size: int | None


class WorkspaceFileContent(BaseModel):
    path: str
    content: str
    size: int


def create_app(
    settings: Settings | None = None,
    inference: ChatEngine | None = None,
    memory_path: Path | None = None,
) -> FastAPI:
    config = settings or Settings.from_env()
    app = FastAPI(title="Lia Core", version="0.4.0")
    app.state.inference = inference or create_inference_client(config)
    app.state.memory = MemoryStore(memory_path or config.data_dir / "memory.sqlite3")
    app.state.workspaces = WorkspaceRegistry(config.dev_workspaces)
    app.state.inference_configured = bool(config.llm_base_url)

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(
            inference="local_endpoint_configured" if app.state.inference_configured else "not_configured"
        )

    @app.post("/api/v1/chat", response_model=ChatResponse)
    async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
        messages = [{"role": item.role, "content": item.content} for item in payload.messages]
        if payload.system:
            messages.insert(0, {"role": "system", "content": payload.system})
        try:
            answer = await request.app.state.inference.complete(
                messages, payload.temperature, payload.max_tokens
            )
        except LocalModelError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "local_model_unavailable",
                    "message": "O modelo local não está disponível. Inicie o servidor llama.cpp.",
                },
            ) from exc
        return ChatResponse(
            content=answer,
            engine=getattr(request.app.state.inference, "engine_name", "llama.cpp"),
        )

    @app.post("/api/v1/memories", response_model=MemoryItem, status_code=status.HTTP_201_CREATED)
    async def create_memory(payload: MemoryCreate, request: Request) -> MemoryItem:
        record = request.app.state.memory.add(payload.kind, payload.content, payload.key)
        return MemoryItem(**record)

    @app.get("/api/v1/memories", response_model=list[MemoryItem])
    async def list_memories(
        request: Request,
        q: str | None = Query(default=None, max_length=200),
        kind: str | None = Query(default=None, pattern="^(fact|preference|knowledge|note)$"),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> list[MemoryItem]:
        return [MemoryItem(**item) for item in request.app.state.memory.list(q, kind, limit)]

    @app.delete("/api/v1/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_memory(memory_id: int, request: Request) -> Response:
        if not request.app.state.memory.delete(memory_id):
            raise HTTPException(status_code=404, detail="Memória não encontrada.")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/api/v1/dev/workspaces", response_model=list[WorkspaceSummary])
    async def list_workspaces(request: Request) -> list[WorkspaceSummary]:
        return [
            WorkspaceSummary(**workspace)
            for workspace in request.app.state.workspaces.list_workspaces()
        ]

    @app.get(
        "/api/v1/dev/workspaces/{workspace_id}/files",
        response_model=list[WorkspaceFileEntry],
    )
    async def list_workspace_files(
        workspace_id: str,
        request: Request,
        path: str = Query(default=".", max_length=1000),
    ) -> list[WorkspaceFileEntry]:
        try:
            entries = request.app.state.workspaces.list_files(workspace_id, path)
        except WorkspaceNotFound as exc:
            raise HTTPException(status_code=404, detail="Workspace não autorizado ou inexistente.") from exc
        except UnsafeWorkspacePath as exc:
            raise HTTPException(status_code=400, detail="Caminho fora do workspace.") from exc
        except WorkspaceItemNotFound as exc:
            raise HTTPException(status_code=404, detail="Diretório não encontrado.") from exc
        return [WorkspaceFileEntry(**entry) for entry in entries]

    @app.get(
        "/api/v1/dev/workspaces/{workspace_id}/file",
        response_model=WorkspaceFileContent,
    )
    async def read_workspace_file(
        workspace_id: str,
        request: Request,
        path: str = Query(..., min_length=1, max_length=1000),
    ) -> WorkspaceFileContent:
        try:
            item = request.app.state.workspaces.read_file(workspace_id, path)
        except WorkspaceNotFound as exc:
            raise HTTPException(status_code=404, detail="Workspace não autorizado ou inexistente.") from exc
        except UnsafeWorkspacePath as exc:
            raise HTTPException(status_code=400, detail="Caminho fora do workspace.") from exc
        except WorkspaceItemNotFound as exc:
            raise HTTPException(status_code=404, detail="Arquivo não encontrado.") from exc
        except SensitiveWorkspaceFile as exc:
            raise HTTPException(status_code=403, detail="Leitura deste arquivo bloqueada por segurança.") from exc
        except WorkspaceFileTooLarge as exc:
            raise HTTPException(status_code=413, detail="Arquivo excede o limite de leitura de 256 KiB.") from exc
        except UnsupportedTextFile as exc:
            raise HTTPException(status_code=415, detail="Arquivo não é texto UTF-8 compatível.") from exc
        return WorkspaceFileContent(**item)

    return app


app = create_app()
