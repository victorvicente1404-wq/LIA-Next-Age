from __future__ import annotations

import httpx

from lia_core.config import Settings


class LocalModelError(RuntimeError):
    """Raised when the configured local inference server cannot answer."""


class LocalInferenceClient:
    """Small adapter for llama.cpp's OpenAI-compatible chat completions endpoint."""

    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.llm_base_url.rstrip("/")
        self.model = settings.llm_model
        self.timeout = settings.request_timeout_seconds

    async def complete(
        self, messages: list[dict[str, str]], temperature: float, max_tokens: int
    ) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise LocalModelError("Local llama.cpp endpoint did not return a valid response") from exc

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LocalModelError("Unexpected response from local inference server") from exc

        if not isinstance(content, str) or not content.strip():
            raise LocalModelError("Local inference server returned an empty response")
        return content.strip()
