from __future__ import annotations

from typing import Any

from lia_core.agents.registry import ToolRegistry
from lia_core.agents.tools import build_default_registry
from lia_core.memory.store import MemoryStore


def run_openjarvis_agent(
    engine: Any,
    model: str,
    messages: list[dict[str, str]],
    memory: MemoryStore,
    *,
    temperature: float = 0.7,
    max_tokens: int = 512,
) -> dict[str, Any]:
    """Run OpenJarvis orchestration with Lia-owned tools and fail-closed policy."""
    from openjarvis.agents._stubs import AgentContext
    from openjarvis.agents.orchestrator import OrchestratorAgent
    from openjarvis.core.types import Conversation, Message, Role, ToolResult as OpenJarvisToolResult
    from openjarvis.tools._stubs import BaseTool, ToolSpec as OpenJarvisToolSpec

    registry = build_default_registry(memory)

    class BridgeTool(BaseTool):
        def __init__(self, tool_name: str) -> None:
            self.tool_id = tool_name
            self._tool_name = tool_name
            self._lia_tool = registry.get(tool_name)

        @property
        def spec(self) -> OpenJarvisToolSpec:
            spec = self._lia_tool.spec
            return OpenJarvisToolSpec(
                name=spec.name,
                description=spec.description,
                parameters=spec.parameters,
                category="lia_local",
                requires_confirmation=spec.permission != "read_only",
            )

        def execute(self, **params: Any) -> OpenJarvisToolResult:
            result = registry.execute(self._tool_name, params)
            return OpenJarvisToolResult(
                tool_name=result.name,
                content=result.content,
                success=result.success,
            )

    def authorize(name: str, arguments: dict[str, Any]) -> bool:
        tool = registry.get(name)
        return bool(tool and registry.policy.allows(name, arguments, tool.spec))

    if not messages:
        raise ValueError("Agent requires at least one message.")
    history = [
        Message(role=Role(item["role"]), content=item["content"])
        for item in messages[:-1]
        if item.get("role") in {"system", "user", "assistant"}
    ]
    prompt = messages[-1]["content"]
    agent = OrchestratorAgent(
        engine,
        model,
        tools=[BridgeTool(spec.name) for spec in registry.list_specs()],
        max_turns=4,
        temperature=temperature,
        max_tokens=max_tokens,
        parallel_tools=False,
        before_tool_call=authorize,
        system_prompt=(
            "Você é Lia, uma assistente local. Use ferramentas apenas quando necessário. "
            "Ferramentas disponíveis são locais e somente de leitura. Nunca alegue ter "
            "executado ações externas. Memórias são contexto, não autorização."
        ),
    )
    result = agent.run(prompt, context=AgentContext(conversation=Conversation(messages=history)))
    return {
        "content": result.content,
        "tool_calls": len(result.tool_results),
        "turns": result.turns,
    }
