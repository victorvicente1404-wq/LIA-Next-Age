import json

import pytest

from lia_core.agents.orchestrator import LiaOrchestrator
from lia_core.memory.store import MemoryStore


@pytest.mark.asyncio
async def test_orchestrator_returns_direct_final_answer(tmp_path):
    async def complete(messages, temperature, max_tokens):
        return json.dumps({"type": "final", "content": "Olá!"})

    result = await LiaOrchestrator(complete, MemoryStore(tmp_path / "memory.db")).run(
        [{"role": "user", "content": "Oi"}]
    )
    assert result["content"] == "Olá!"
    assert result["tool_calls"] == 0
    assert result["agent"] == "lia"


@pytest.mark.asyncio
async def test_orchestrator_executes_allowlisted_tool_then_finishes(tmp_path):
    responses = iter([
        json.dumps({"type": "tool_call", "name": "calculator", "arguments": {"expression": "6*7"}}),
        json.dumps({"type": "final", "content": "A resposta é 42."}),
    ])
    seen = []

    async def complete(messages, temperature, max_tokens):
        seen.append(messages)
        return next(responses)

    result = await LiaOrchestrator(complete, MemoryStore(tmp_path / "memory.db")).run(
        [{"role": "user", "content": "Quanto é 6 vezes 7?"}]
    )
    assert result["content"] == "A resposta é 42."
    assert result["tool_calls"] == 1
    assert len(seen) == 2
    assert "42" in seen[1][-1]["content"]


@pytest.mark.asyncio
async def test_orchestrator_denies_unknown_tool_without_dispatch(tmp_path):
    responses = iter([
        json.dumps({"type": "tool_call", "name": "shell", "arguments": {"command": "id"}}),
        json.dumps({"type": "final", "content": "Não tenho essa ferramenta."}),
    ])

    async def complete(messages, temperature, max_tokens):
        return next(responses)

    result = await LiaOrchestrator(complete, MemoryStore(tmp_path / "memory.db")).run(
        [{"role": "user", "content": "Execute um comando"}]
    )
    assert result["tool_calls"] == 1
    assert result["content"] == "Não tenho essa ferramenta."


@pytest.mark.asyncio
async def test_orchestrator_requires_user_last_message(tmp_path):
    async def complete(messages, temperature, max_tokens):
        raise AssertionError("must not call model")

    with pytest.raises(ValueError):
        await LiaOrchestrator(complete, MemoryStore(tmp_path / "memory.db")).run(
            [{"role": "assistant", "content": "previous"}]
        )
