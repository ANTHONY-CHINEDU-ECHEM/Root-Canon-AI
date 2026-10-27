"""OpenAI provider (switchable alternative)."""

from __future__ import annotations

from collections.abc import AsyncIterator

from backend.app.llm.base import LLMMessage, LLMProvider, LLMResponse, LLMUnavailableError


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, api_key: str | None, model: str, timeout: float = 60.0) -> None:
        if not api_key:
            raise LLMUnavailableError("OPENAI_API_KEY is not set")
        from openai import AsyncOpenAI

        self.client = AsyncOpenAI(api_key=api_key, timeout=timeout, max_retries=3)
        self.model = model

    @staticmethod
    def _messages(system: str, messages: list[LLMMessage]) -> list[dict]:
        return [{"role": "system", "content": system}, *({"role": m.role, "content": m.content} for m in messages)]

    async def complete(self, system: str, messages: list[LLMMessage], *,
                       temperature: float, max_tokens: int) -> LLMResponse:
        response = await self.client.chat.completions.create(
            model=self.model, messages=self._messages(system, messages),
            temperature=temperature, max_tokens=max_tokens,
        )
        choice = response.choices[0]
        usage = response.usage
        return LLMResponse(text=choice.message.content or "", model=response.model, provider=self.name,
                           input_tokens=usage.prompt_tokens if usage else 0,
                           output_tokens=usage.completion_tokens if usage else 0,
                           stop_reason=choice.finish_reason)

    async def stream(self, system: str, messages: list[LLMMessage], *,
                     temperature: float, max_tokens: int) -> AsyncIterator[str]:
        stream = await self.client.chat.completions.create(
            model=self.model, messages=self._messages(system, messages),
            temperature=temperature, max_tokens=max_tokens, stream=True,
        )
        async for event in stream:
            if event.choices and event.choices[0].delta.content:
                yield event.choices[0].delta.content
