"""Ollama provider for fully local inference.

Useful for practices that cannot send any query text off site. Talks to the
Ollama HTTP API directly so no extra SDK is required.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from backend.app.llm.base import LLMMessage, LLMProvider, LLMResponse, LLMUnavailableError


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, base_url: str, model: str, timeout: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.client = httpx.AsyncClient(timeout=timeout)

    def _payload(self, system: str, messages: list[LLMMessage], temperature: float,
                 max_tokens: int, stream: bool) -> dict:
        return {
            "model": self.model, "stream": stream,
            "messages": [{"role": "system", "content": system},
                         *({"role": m.role, "content": m.content} for m in messages)],
            "options": {"temperature": temperature, "num_predict": max_tokens, "num_ctx": 16384},
        }

    async def complete(self, system: str, messages: list[LLMMessage], *,
                       temperature: float, max_tokens: int) -> LLMResponse:
        try:
            response = await self.client.post(f"{self.base_url}/api/chat",
                                              json=self._payload(system, messages, temperature, max_tokens, False))
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMUnavailableError(f"Ollama unavailable: {exc}") from exc
        body = response.json()
        return LLMResponse(text=body.get("message", {}).get("content", ""), model=self.model, provider=self.name,
                           input_tokens=body.get("prompt_eval_count", 0), output_tokens=body.get("eval_count", 0),
                           stop_reason=body.get("done_reason"))

    async def stream(self, system: str, messages: list[LLMMessage], *,
                     temperature: float, max_tokens: int) -> AsyncIterator[str]:
        async with self.client.stream("POST", f"{self.base_url}/api/chat",
                                      json=self._payload(system, messages, temperature, max_tokens, True)) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.strip():
                    chunk = json.loads(line)
                    if text := chunk.get("message", {}).get("content"):
                        yield text

    async def health(self) -> bool:
        try:
            response = await self.client.get(f"{self.base_url}/api/tags", timeout=3)
            return response.status_code == 200
        except httpx.HTTPError:
            return False
