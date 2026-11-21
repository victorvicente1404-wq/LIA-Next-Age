from fastapi.testclient import TestClient

from lia_core.config import Settings
from lia_core.inference.llamacpp import LocalModelError
from lia_core.main import create_app


class FakeInference:
    engine_name = "fake-local"

    def __init__(self, *, agent_result=None, agent_error=None):
        self.agent_result = agent_result or {
            "content": "Resposta do agente",
            "tool_calls": 2,
            "turns": 3,
            "agent": "lia",
            "specialist": "engineering",
            "plan": ["Calcular", "Explicar"],
        }
        self.agent_error = agent_error
        self.agent_calls = 0
        self.complete_calls = 0
        self.agent_messages = None

    async def complete(self, messages, temperature, max_tokens):
        self.complete_calls += 1
        return "Resposta simples"

    async def complete_with_agent(self, messages, temperature, max_tokens, memory):
        self.agent_calls += 1
        self.agent_messages = messages
        if self.agent_error:
            raise self.agent_error
        return self.agent_result


def make_client(tmp_path, inference):
    settings = Settings(
        llm_base_url="http://127.0.0.1:8080/v1",
        llm_model="test-model",
        data_dir=tmp_path,
    )
    return TestClient(create_app(settings=settings, inference=inference), client=("127.0.0.1", 12345))


def test_chat_uses_agent_for_user_turn_and_returns_agent_metadata(tmp_path):
    inference = FakeInference()
    with make_client(tmp_path, inference) as client:
        response = client.post(
            "/api/v1/chat",
            json={"messages": [{"role": "user", "content": "Quanto é 2+2?"}]},
        )

    assert response.status_code == 200
    assert response.json()["content"] == "Resposta do agente"
    assert response.json()["agent"] == "lia"
    assert response.json()["specialist"] == "engineering"
    assert response.json()["tool_calls"] == 2
    assert response.json()["agent_turns"] == 3
    assert response.json()["plan"] == ["Calcular", "Explicar"]
    assert inference.agent_calls == 1
    assert inference.complete_calls == 0


def test_chat_skips_agent_when_tools_are_disabled(tmp_path):
    inference = FakeInference()
    with make_client(tmp_path, inference) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "messages": [{"role": "user", "content": "Olá"}],
                "use_tools": False,
            },
        )

    assert response.status_code == 200
    assert response.json()["content"] == "Resposta simples"
    assert response.json()["agent"] == "simple"
    assert inference.agent_calls == 0
    assert inference.complete_calls == 1


def test_chat_falls_back_to_simple_completion_when_history_ends_with_assistant(tmp_path):
    inference = FakeInference()
    with make_client(tmp_path, inference) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "messages": [
                    {"role": "user", "content": "Pergunta anterior"},
                    {"role": "assistant", "content": "Resposta anterior"},
                ]
            },
        )

    assert response.status_code == 200
    assert response.json()["content"] == "Resposta simples"
    assert response.json()["agent"] == "simple"
    assert inference.agent_calls == 0
    assert inference.complete_calls == 1


def test_agent_local_model_error_returns_503_without_simple_fallback(tmp_path):
    inference = FakeInference(agent_error=LocalModelError("local engine unavailable"))
    with make_client(tmp_path, inference) as client:
        response = client.post(
            "/api/v1/chat",
            json={"messages": [{"role": "user", "content": "Olá"}]},
        )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "local_model_unavailable"
    assert inference.agent_calls == 1
    assert inference.complete_calls == 0
