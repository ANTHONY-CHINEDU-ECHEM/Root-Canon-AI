"""Provider neutral LLM interface.

All providers implement the same two methods so the RAG pipeline never knows
which vendor it is talking to. Switching is a configuration change
(RC_LLM_PROVIDER) or a per request override from the interface.
"""

from __future__ import annotations

import abc
from collections.abc import AsyncIterator
from dataclasses import dataclass, field


@dataclass
class LLMMessage:
    role: str  # "user" | "assistant"
    content: str


@dataclass
class LLMResponse:
    text: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str | None = None
    raw: dict = field(default_factory=dict)


class LLMProvider(abc.ABC):
    name: str

    @abc.abstractmethod
    async def complete(self, system: str, messages: list[LLMMessage], *,
                       temperature: float, max_tokens: int) -> LLMResponse: ...

    @abc.abstractmethod
    def stream(self, system: str, messages: list[LLMMessage], *,
               temperature: float, max_tokens: int) -> AsyncIterator[str]: ...

    async def health(self) -> bool:
        return True


class LLMUnavailableError(RuntimeError):
    """Raised when a provider is not configured or cannot be reached."""
