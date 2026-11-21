from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    permission: str = "read_only"


@dataclass(frozen=True, slots=True)
class ToolResult:
    name: str
    content: str
    success: bool = True


class LiaTool(Protocol):
    @property
    def spec(self) -> ToolSpec: ...

    def execute(self, **arguments: Any) -> ToolResult: ...


class ToolPolicy:
    """Fail-closed policy for tools exposed to an agent."""

    def __init__(self, allowed_read_only: set[str] | None = None) -> None:
        self._allowed_read_only = set(allowed_read_only or ())

    def allows(self, name: str, arguments: dict[str, Any], spec: ToolSpec) -> bool:
        if not isinstance(arguments, dict):
            return False
        return spec.permission == "read_only" and name in self._allowed_read_only


class ToolRegistry:
    """Small explicit registry; unknown tools are never dispatched."""

    def __init__(self, policy: ToolPolicy | None = None) -> None:
        self._tools: dict[str, LiaTool] = {}
        self.policy = policy or ToolPolicy()

    def register(self, tool: LiaTool) -> None:
        name = tool.spec.name
        if not name or name in self._tools:
            raise ValueError("Tool name is empty or already registered.")
        self._tools[name] = tool

    def list_specs(self) -> list[ToolSpec]:
        return [tool.spec for tool in self._tools.values()]

    def get(self, name: str) -> LiaTool | None:
        return self._tools.get(name)

    def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(name, "Ferramenta desconhecida ou indisponível.", False)
        if not self.policy.allows(name, arguments, tool.spec):
            return ToolResult(name, "A política da Lia bloqueou esta execução.", False)
        try:
            return tool.execute(**arguments)
        except (TypeError, ValueError) as exc:
            return ToolResult(name, f"Argumentos inválidos: {exc}", False)
        except Exception:  # noqa: BLE001 - isolate tool failures from the agent loop
            return ToolResult(name, "A ferramenta falhou; detalhes internos foram ocultados.", False)
