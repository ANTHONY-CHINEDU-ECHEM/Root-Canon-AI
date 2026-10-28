import pytest

from backend.app.config import Settings
from backend.app.llm.base import LLMMessage, LLMProvider, LLMResponse, LLMUnavailableError
from backend.app.llm.factory import ExtractiveProvider, build_router
from backend.app.llm.router import CircuitBreaker, ProviderRouter

MSG = [LLMMessage("user", '<sources>\n<source id="1" title="t">Amoxicillin 500 mg three times daily for adults.'
                          "</source>\n</sources>\n\n<question>amoxicillin dose for adults</question>")]


class Flaky(LLMProvider):
    def __init__(self, name: str, fail: bool = True, fail_after_tokens: int | None = None) -> None:
        self.name = name
        self.model = f"{name}-model"
        self.fail = fail
        self.fail_after_tokens = fail_after_tokens
        self.calls = 0

    async def complete(self, system, messages, *, temperature, max_tokens):
        self.calls += 1
        if self.fail:
            raise ConnectionError("vendor down")
        return LLMResponse("ok [1].", self.model, self.name, input_tokens=10, output_tokens=3)

    async def stream(self, system, messages, *, temperature, max_tokens):
        self.calls += 1
        for i, token in enumerate(["first ", "second ", "third"]):
            if self.fail and (self.fail_after_tokens is None or i >= self.fail_after_tokens):
                raise TimeoutError("vendor timeout")
            yield token


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_circuit_breaker_opens_and_half_opens():
    clock = Clock()
    breaker = CircuitBreaker(failure_threshold=2, cooldown_seconds=10, clock=clock)
    breaker.failure()
    assert breaker.allow()
    breaker.failure()
    assert breaker.state == "open" and not breaker.allow()
    clock.now = 11
    assert breaker.state == "half_open" and breaker.allow()
    breaker.failure()  # trial request failed: open again immediately
    assert breaker.state == "open"
    clock.now = 25
    breaker.success()
    assert breaker.state == "closed"


@pytest.mark.asyncio
async def test_router_falls_back_in_order_and_records_provider():
    primary, secondary = Flaky("primary"), Flaky("secondary", fail=False)
    router = ProviderRouter([primary, secondary, ExtractiveProvider()])
    response = await router.complete("s", MSG, temperature=0, max_tokens=10)
    assert response.provider == "secondary" and router.last_used is secondary


@pytest.mark.asyncio
async def test_router_skips_open_circuit():
    primary = Flaky("primary")
    router = ProviderRouter([primary, ExtractiveProvider()], failure_threshold=1, cooldown_seconds=60)
    await router.complete("s", MSG, temperature=0, max_tokens=10)
    await router.complete("s", MSG, temperature=0, max_tokens=10)
    assert primary.calls == 1
    assert router.status()[0]["circuit"] == "open"


@pytest.mark.asyncio
async def test_stream_falls_back_before_first_token():
    router = ProviderRouter([Flaky("primary", fail_after_tokens=0), ExtractiveProvider()])
    text = "".join([t async for t in router.stream("s", MSG, temperature=0, max_tokens=10)])
    assert "Amoxicillin 500 mg" in text and router.last_used.name == "extractive"


@pytest.mark.asyncio
async def test_stream_failure_mid_answer_is_not_mixed_with_another_model():
    router = ProviderRouter([Flaky("primary", fail_after_tokens=2), ExtractiveProvider()])
    received = []
    with pytest.raises(LLMUnavailableError):
        async for token in router.stream("s", MSG, temperature=0, max_tokens=10):
            received.append(token)
    assert received == ["first ", "second "]


def test_build_router_without_keys_is_extractive_only():
    settings = Settings(_env_file=None, llm_provider="anthropic", llm_fallbacks=["openai"])
    assert isinstance(build_router(settings), ExtractiveProvider)


def test_build_router_chains_ollama_then_extractive():
    settings = Settings(_env_file=None, llm_provider="ollama", llm_fallbacks=["openai", "ollama"])
    router = build_router(settings)
    assert isinstance(router, ProviderRouter)
    assert [p.name for p in router.providers] == ["ollama", "extractive"]


@pytest.mark.asyncio
async def test_pipeline_survives_total_vendor_outage(settings, retriever):
    from backend.app.generation.rag_pipeline import RAGPipeline

    pipeline = RAGPipeline(settings, retriever, ProviderRouter([Flaky("anthropic"), ExtractiveProvider()]))
    result = await pipeline.answer("What is the adult ibuprofen dose for dental pain?")
    assert result.provider == "extractive" and not result.abstained and result.sources
