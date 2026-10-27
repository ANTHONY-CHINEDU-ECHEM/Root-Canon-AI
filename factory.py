"""Provider factory and an extractive provider for tests and offline demos."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator

from backend.app.config import Settings
from backend.app.llm.base import LLMMessage, LLMProvider, LLMResponse

_SOURCE_BLOCK = re.compile(r"<source id=\"(\d+)\"[^>]*>\s*(.*?)\s*</source>", re.DOTALL)


class ExtractiveProvider(LLMProvider):
    """Deterministic, grounded fallback used in tests and when no API key is set.

    It builds an answer only from sentences present in the supplied sources,
    each carrying its citation, so it can never hallucinate. It is deliberately
    plain: it exists to make the system testable end to end, not to replace a
    real model.
    """

    name = "extractive"

    def _answer(self, prompt: str) -> str:
        question = prompt.rsplit("<question>", 1)[-1].split("</question>", 1)[0].lower()
        q_terms = {w for w in re.findall(r"[a-z]{4,}", question)}
        scored = []
        for source_id, body in _SOURCE_BLOCK.findall(prompt):
            text = body.split("\n", 1)[-1]
            for sentence in re.split(r"(?<=[.!?])\s+", text):
                overlap = len(q_terms & set(re.findall(r"[a-z]{4,}", sentence.lower())))
                if overlap and len(sentence) > 30:
                    scored.append((overlap, int(source_id), sentence.strip()))
        if not scored:
            return "INSUFFICIENT_EVIDENCE"
        scored.sort(key=lambda t: (-t[0], t[1]))
        threshold = max(1, scored[0][0] // 2)
        kept = [item for item in scored if item[0] >= threshold] or scored[:1]
        lines = [f"{s.rstrip('.')} [{sid}]." for _, sid, s in kept[:4]]
        return "**Summary of the retrieved evidence**\n\n" + "\n".join(f"* {line}" for line in lines)

    async def complete(self, system: str, messages: list[LLMMessage], *,
                       temperature: float, max_tokens: int) -> LLMResponse:
        text = self._answer(messages[-1].content)
        return LLMResponse(text=text, model="extractive", provider=self.name)

    async def stream(self, system: str, messages: list[LLMMessage], *,
                     temperature: float, max_tokens: int) -> AsyncIterator[str]:
        for token in re.split(r"(\s+)", self._answer(messages[-1].content)):
            yield token


def build_provider(settings: Settings, override: str | None = None) -> LLMProvider:
    name = override or settings.llm_provider
    if name == "anthropic" and settings.anthropic_api_key:
        from backend.app.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(settings.anthropic_api_key.get_secret_value(), settings.anthropic_model,
                                 settings.llm_timeout_seconds)
    if name == "openai" and settings.openai_api_key:
        from backend.app.llm.openai_provider import OpenAIProvider

        return OpenAIProvider(settings.openai_api_key.get_secret_value(), settings.openai_model,
                              settings.llm_timeout_seconds)
    if name == "ollama":
        from backend.app.llm.ollama_provider import OllamaProvider

        return OllamaProvider(settings.ollama_base_url, settings.ollama_model)
    return ExtractiveProvider()
