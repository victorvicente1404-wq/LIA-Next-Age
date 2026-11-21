from __future__ import annotations

import math
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

    @staticmethod
    def _validate_arguments(spec: ToolSpec, arguments: dict[str, Any]) -> str | None:
        """Validate the strict, flat JSON-schema subset used by local tools."""
        schema = spec.parameters
        if not isinstance(schema, dict) or schema.get("type") != "object":
            return "Esquema de parâmetros inválido."
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if (
            not isinstance(properties, dict)
            or not isinstance(required, list)
            or schema.get("additionalProperties", False) is not False
        ):
            return "Esquema de parâmetros inválido."
        if any(not isinstance(key, str) for key in required):
            return "Esquema de parâmetros inválido."
        if any(key not in properties for key in required):
            return "Esquema de parâmetros inválido."
        if any(key not in properties for key in arguments):
            return "Parâmetro não permitido."
        if any(key not in arguments for key in required):
            return "Parâmetro obrigatório ausente."

        for key, value in arguments.items():
            definition = properties.get(key)
            if not isinstance(definition, dict):
                return "Definição de parâmetro inválida."
            expected = definition.get("type")
            valid_types = {
                "string": lambda item: isinstance(item, str),
                "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
                "number": lambda item: (
                    isinstance(item, (int, float))
                    and not isinstance(item, bool)
                    and (not isinstance(item, float) or math.isfinite(item))
                ),
                "boolean": lambda item: isinstance(item, bool),
            }
            if expected not in valid_types or not valid_types[expected](value):
                return f"Tipo inválido para o parâmetro '{key}'."
            if isinstance(value, str):
                if len(value) < definition.get("minLength", 0):
                    return f"O parâmetro '{key}' é muito curto."
                if len(value) > definition.get("maxLength", float("inf")):
                    return f"O parâmetro '{key}' é muito longo."
            if isinstance(value, list):
                if len(value) < definition.get("minItems", 0):
                    return f"O parâmetro '{key}' tem poucos itens."
                if len(value) > definition.get("maxItems", float("inf")):
                    return f"O parâmetro '{key}' tem itens demais."
        return None

    def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(name, "Ferramenta desconhecida ou indisponível.", False)
        if not self.policy.allows(name, arguments, tool.spec):
            return ToolResult(name, "A política da Lia bloqueou esta execução.", False)
        validation_error = self._validate_arguments(tool.spec, arguments)
        if validation_error:
            return ToolResult(name, validation_error, False)
        try:
            return tool.execute(**arguments)
        except (TypeError, ValueError) as exc:
            return ToolResult(name, f"Argumentos inválidos: {exc}", False)
        except Exception:  # noqa: BLE001 - isolate tool failures from the agent loop
            return ToolResult(
                name, "A ferramenta falhou; detalhes internos foram ocultados.", False
            )
