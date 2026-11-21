import asyncio
import json

from lia_core.agents.orchestrator import LiaOrchestrator
from lia_core.memory.store import MemoryStore


def test_orchestrator_returns_direct_final_answer(tmp_path):
    async def complete(messages, temperature, max_tokens):
        return json.dumps({"type": "final", "content": "Olá!"})

    result = asyncio.run(LiaOrchestrator(complete, MemoryStore(tmp_path / "memory.db")).run(
        [{"role": "user", "content": "Oi"}]
    ))
    assert result["content"] == "Olá!"
    assert result["tool_calls"] == 0
    assert result["agent"] == "lia"


def test_orchestrator_executes_allowlisted_tool_then_finishes(tmp_path):
    responses = iter([
        json.dumps({"type": "tool_call", "name": "calculator", "arguments": {"expression": "6*7"}}),
        json.dumps({"type": "final", "content": "A resposta é 42."}),
    ])
    seen = []

    async def complete(messages, temperature, max_tokens):
        seen.append(messages)
        return next(responses)

    result = asyncio.run(LiaOrchestrator(complete, MemoryStore(tmp_path / "memory.db")).run(
        [{"role": "user", "content": "Quanto é 6 vezes 7?"}]
    ))
    assert result["content"] == "A resposta é 42."
    assert result["tool_calls"] == 1
    assert len(seen) == 2
    assert "42" in seen[1][-1]["content"]


def test_orchestrator_denies_unknown_tool_without_dispatch(tmp_path):
    responses = iter([
        json.dumps({"type": "tool_call", "name": "shell", "arguments": {"command": "id"}}),
        json.dumps({"type": "final", "content": "Não tenho essa ferramenta."}),
    ])

    async def complete(messages, temperature, max_tokens):
        return next(responses)

    result = asyncio.run(LiaOrchestrator(complete, MemoryStore(tmp_path / "memory.db")).run(
        [{"role": "user", "content": "Execute um comando"}]
    ))
    assert result["tool_calls"] == 1
    assert result["content"] == "Não tenho essa ferramenta."


def test_orchestrator_requires_user_last_message(tmp_path):
    async def complete(messages, temperature, max_tokens):
        raise AssertionError("must not call model")

    try:
        asyncio.run(LiaOrchestrator(complete, MemoryStore(tmp_path / "memory.db")).run(
            [{"role": "assistant", "content": "previous"}]
        ))
    except ValueError:
        pass
    else:
        raise AssertionError("orchestrator accepted an assistant-ending history")

def test_orchestrator_keeps_bounded_plan_and_executes_next_tool(tmp_path):
    responses = iter([
        json.dumps({
            "type": "plan",
            "goal": "Calcular e explicar",
            "steps": ["Calcular 6 vezes 7", "Explicar o resultado"],
        }),
        json.dumps({
            "type": "tool_call",
            "name": "calculator",
            "arguments": {"expression": "6*7"},
        }),
        json.dumps({"type": "final", "content": "O resultado é 42."}),
    ])

    async def complete(messages, temperature, max_tokens):
        return next(responses)

    result = asyncio.run(LiaOrchestrator(complete, MemoryStore(tmp_path / "memory.db")).run(
        [{"role": "user", "content": "Calcule 6 vezes 7 e explique."}]
    ))

    assert result["content"] == "O resultado é 42."
    assert result["plan"] == ["Calcular 6 vezes 7", "Explicar o resultado"]
    assert result["tool_calls"] == 1
