from __future__ import annotations

import ast
import math
import operator
from typing import Any, ClassVar

from lia_core.agents.registry import ToolPolicy, ToolRegistry, ToolResult, ToolSpec
from lia_core.memory.store import MemoryStore


class CalculatorTool:
    """Evaluate a small arithmetic grammar without eval or code execution."""

    _binary: ClassVar[dict[type[ast.operator], Any]] = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
    }
    _unary: ClassVar[dict[type[ast.unaryop], Any]] = {ast.UAdd: operator.pos, ast.USub: operator.neg}

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="calculator",
            description="Calcula uma expressão aritmética simples.",
            parameters={
                "type": "object",
                "properties": {"expression": {"type": "string", "maxLength": 160}},
                "required": ["expression"],
                "additionalProperties": False,
            },
        )

    def execute(self, expression: str) -> ToolResult:
        if not isinstance(expression, str) or len(expression) > 160:
            raise ValueError("A expressão é muito longa.")
        try:
            root = ast.parse(expression, mode="eval")
            value = self._evaluate(root.body)
        except (SyntaxError, ZeroDivisionError, OverflowError) as exc:
            raise ValueError("Expressão aritmética inválida.") from exc
        if not math.isfinite(float(value)) or abs(value) > 1e15:
            raise ValueError("Resultado fora do limite permitido.")
        return ToolResult(self.spec.name, str(value))

    def _evaluate(self, node: ast.AST) -> float | int:
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            if abs(node.value) > 1e12:
                raise ValueError("Número fora do limite permitido.")
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in self._binary:
            left, right = self._evaluate(node.left), self._evaluate(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 8:
                raise ValueError("Expoente fora do limite permitido.")
            return self._binary[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in self._unary:
            return self._unary[type(node.op)](self._evaluate(node.operand))
        raise ValueError("A expressão contém operações não permitidas.")


class MemorySearchTool:
    def __init__(self, memory: MemoryStore) -> None:
        self._memory = memory

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="memory_search",
            description="Pesquisa memórias que o usuário salvou explicitamente.",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string", "minLength": 1, "maxLength": 200}},
                "required": ["query"],
                "additionalProperties": False,
            },
        )

    def execute(self, query: str) -> ToolResult:
        if not isinstance(query, str) or not query.strip() or len(query) > 200:
            raise ValueError("A busca precisa ter entre 1 e 200 caracteres.")
        matches = self._memory.relevant(query.strip(), limit=5)
        if not matches:
            return ToolResult(self.spec.name, "Nenhuma memória relevante encontrada.")
        lines = [f"- [{item['kind']}] {item['content']}" for item in matches]
        return ToolResult(self.spec.name, "\n".join(lines))


def build_default_registry(memory: MemoryStore) -> ToolRegistry:
    """Only low-risk, local, read-only tools are exposed by default."""
    registry = ToolRegistry(ToolPolicy({"calculator", "memory_search"}))
    for tool in (CalculatorTool(), MemorySearchTool(memory)):
        registry.register(tool)
    return registry
