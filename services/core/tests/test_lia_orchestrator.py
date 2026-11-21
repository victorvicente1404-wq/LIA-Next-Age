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

def test_orchestrator_routes_to_memory_profile_and_narrows_tools(tmp_path):
    memory = MemoryStore(tmp_path / "memory.db")
    memory.add("fact", "A Lia usa SQLite para memória local.")
    responses = iter([
        json.dumps({"type": "specialist", "name": "memory"}),
        json.dumps({
            "type": "tool_call",
            "name": "memory_search",
            "arguments": {"query": "SQLite"},
        }),
        json.dumps({"type": "final", "content": "A memória da Lia usa SQLite."}),
    ])
    seen = []

    async def complete(messages, temperature, max_tokens):
        seen.append(messages)
        return next(responses)

    result = asyncio.run(LiaOrchestrator(complete, memory).run([
        {"role": "user", "content": "Como você guarda sua memória?"}
    ]))

    assert result["specialist"] == "memory"
    assert result["tool_calls"] == 1
    assert len(seen) == 3
    assert "Perfil ativo: memory" in seen[1][0]["content"]
    assert "memory_search(query: string)" in seen[1][0]["content"]
    assert "calculator(expression: string)" not in seen[1][0]["content"]
    assert "SQLite" in seen[2][-1]["content"]


def test_memory_profile_cannot_call_calculator(tmp_path):
    responses = iter([
        json.dumps({"type": "specialist", "name": "memory"}),
        json.dumps({
            "type": "tool_call",
            "name": "calculator",
            "arguments": {"expression": "6*7"},
        }),
        json.dumps({"type": "final", "content": "Esse perfil não tem calculadora."}),
    ])
    seen = []

    async def complete(messages, temperature, max_tokens):
        seen.append(messages)
        return next(responses)

    result = asyncio.run(LiaOrchestrator(
        complete, MemoryStore(tmp_path / "memory.db")
    ).run([{"role": "user", "content": "Quanto é 6 vezes 7?"}]))

    assert result["specialist"] == "memory"
    assert "política da Lia bloqueou" in seen[2][-1]["content"]


def test_orchestrator_rejects_second_specialist_switch(tmp_path):
    responses = iter([
        json.dumps({"type": "specialist", "name": "memory"}),
        json.dumps({"type": "specialist", "name": "engineering"}),
    ])

    async def complete(messages, temperature, max_tokens):
        return next(responses)

    result = asyncio.run(LiaOrchestrator(
        complete, MemoryStore(tmp_path / "memory.db")
    ).run([{"role": "user", "content": "Lembre de algo e explique código."}]))

    assert result["specialist"] == "memory"
    assert "não posso trocar novamente" in result["content"]


def test_orchestrator_rejects_unknown_specialist(tmp_path):
    async def complete(messages, temperature, max_tokens):
        return json.dumps({"type": "specialist", "name": "shell"})

    result = asyncio.run(LiaOrchestrator(
        complete, MemoryStore(tmp_path / "memory.db")
    ).run([{"role": "user", "content": "Faça algo."}]))

    assert result["specialist"] == "general"
    assert "Não reconheci esse perfil" in result["content"]

