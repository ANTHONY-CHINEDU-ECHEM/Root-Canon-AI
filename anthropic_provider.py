"""Anthropic Claude provider (default).

Uses the official SDK with prompt caching on the system prompt, which is long
and identical across requests, so repeat questions are cheaper and faster.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from backend.app.llm.base import LLMMessage, LLMProvider, LLMResponse, LLMUnavailableError


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str | None, model: str, timeout: float = 60.0) -> None:
        if not api_key:
            raise LLMUnavailableError("ANTHROPIC_API_KEY is not set")
        from anthropic import AsyncAnthropic

        self.client = AsyncAnthropic(api_key=api_key, timeout=timeout, max_retries=3)
        self.model = model

    @staticmethod
    def _system(system: str) -> list[dict]:
        return [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]

    async def complete(self, system: str, messages: list[LLMMessage], *,
                       temperature: float, max_tokens: int) -> LLMResponse:
        response = await self.client.messages.create(
            model=self.model, system=self._system(system), temperature=temperature, max_tokens=max_tokens,
            messages=[{"role": m.role, "content": m.content} for m in messages],
        )
        text = "".join(block.text for block in response.content if getattr(block, "type", "") == "text")
        return LLMResponse(text=text, model=response.model, provider=self.name,
                           input_tokens=response.usage.input_tokens, output_tokens=response.usage.output_tokens,
                           stop_reason=response.stop_reason)

    async def stream(self, system: str, messages: list[LLMMessage], *,
                     temperature: float, max_tokens: int) -> AsyncIterator[str]:
        async with self.client.messages.stream(
            model=self.model, system=self._system(system), temperature=temperature, max_tokens=max_tokens,
            messages=[{"role": m.role, "content": m.content} for m in messages],
        ) as stream:
            async for text in stream.text_stream:
                yield text
