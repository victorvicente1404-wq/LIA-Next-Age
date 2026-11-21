from __future__ import annotations

import asyncio
from typing import Any

from lia_core.config import Settings
from lia_core.inference.llamacpp import LocalModelError
from lia_core.memory.store import MemoryStore


class OpenJarvisInferenceClient:
    """Use OpenJarvis's local engine and optional local agent orchestration."""

    engine_name = "OpenJarvis / llama.cpp"
    agent_name = "OpenJarvis Orchestrator"

    def __init__(self, settings: Settings) -> None:
        from openjarvis.core.types import Message, Role
        from openjarvis.engine.openai_compat_engines import LlamaCppEngine

        self._message_type = Message
        self._role_type = Role
        self.model = settings.llm_model
        self._temperature = settings.temperature if hasattr(settings, "temperature") else 0.7
        host = settings.llm_base_url.removesuffix("/v1").rstrip("/")
        self._engine = LlamaCppEngine(
            host=host,
            timeout=settings.request_timeout_seconds,
        )

    async def complete(
        self, messages: list[dict[str, str]], temperature: float, max_tokens: int
    ) -> str:
        try:
            typed_messages = [
                self._message_type(
                    role=self._role_type(message["role"]),
                    content=message["content"],
                )
                for message in messages
            ]
            result = await asyncio.to_thread(
                self._engine.generate,
                typed_messages,
                model=self.model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            raise LocalModelError("OpenJarvis could not complete the local inference request") from exc

        content = result.get("content") if isinstance(result, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise LocalModelError("OpenJarvis returned an empty local response")
        return content.strip()

    async def complete_with_agent(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        memory: MemoryStore,
    ) -> dict[str, Any]:
        from lia_core.agents.openjarvis import run_openjarvis_agent

        try:
            result = await asyncio.to_thread(
                run_openjarvis_agent,
                self._engine,
                self.model,
                messages,
                memory,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            raise LocalModelError("OpenJarvis agent orchestration failed") from exc
        if not isinstance(result.get("content"), str) or not result["content"].strip():
            raise LocalModelError("OpenJarvis agent returned an empty response")
        return result
