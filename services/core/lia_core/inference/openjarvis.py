from __future__ import annotations

import asyncio

from lia_core.config import Settings
from lia_core.inference.llamacpp import LocalModelError


class OpenJarvisInferenceClient:
    """Use OpenJarvis's LlamaCppEngine while keeping the model endpoint local."""

    engine_name = "OpenJarvis / llama.cpp"

    def __init__(self, settings: Settings) -> None:
        from openjarvis.core.types import Message, Role
        from openjarvis.engine.openai_compat_engines import LlamaCppEngine

        self._message_type = Message
        self._role_type = Role
        self.model = settings.llm_model
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
