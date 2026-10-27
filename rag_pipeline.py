"""The Root Canon question answering pipeline.

    question
      -> PII redaction            (nothing identifiable leaves the service)
      -> emergency triage         (action banner returned immediately)
      -> scope check              (non dental questions declined, no LLM call)
      -> query building           (history aware, emergency hints, abbreviations)
      -> hybrid retrieval         (dense + BM25 + RRF + rerank + clinical priors)
      -> injection filter         (untrusted chunks dropped)
      -> evidence gate            (abstain if the best evidence is too weak)
      -> generation               (Claude by default, OpenAI or Ollama on demand)
      -> citation validation      (invalid ids removed, numbers checked)
      -> audit record             (hashed question, sources, scores, latency)

The same pipeline powers the blocking /ask endpoint and the streaming /ask/stream
endpoint; the streaming path yields typed events the interface renders live.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass, field

from backend.app.config import Settings
from backend.app.domain import RetrievedChunk
from backend.app.generation.citations import ABSTAIN_MESSAGE, CitationReport, validate
from backend.app.generation.prompts import SYSTEM_PROMPT, build_user_prompt
from backend.app.guardrails import emergency, pii, scope
from backend.app.llm.base import LLMMessage, LLMProvider, LLMUnavailableError
from backend.app.llm.factory import ExtractiveProvider
from backend.app.logging_setup import get_logger
from backend.app.observability import metrics
from backend.app.retrieval.hybrid import HybridRetriever, RetrievalTrace
from ingestion.processing.evidence import EVIDENCE_LABELS

log = get_logger("rag")


@dataclass
class SourceView:
    id: int
    title: str
    url: str
    section: str | None
    source: str
    source_type: str
    evidence: str
    evidence_level: int
    year: int | None
    jurisdiction: str | None
    snippet: str
    score: float

    @classmethod
    def from_retrieved(cls, index: int, item: RetrievedChunk) -> SourceView:
        c = item.chunk
        return cls(index, c.title, c.url, c.section, c.source, c.source_type.value, EVIDENCE_LABELS[c.evidence_level],
                   int(c.evidence_level), c.published_year, c.jurisdiction, c.text[:600], round(item.final_score, 4))


@dataclass
class AnswerResult:
    request_id: str
    answer: str
    sources: list[SourceView]
    emergency_banner: str | None
    abstained: bool
    out_of_scope: bool
    grounded: bool
    citation_coverage: float
    unsupported_numbers: list[str]
    redactions: dict[str, int]
    provider: str
    model: str
    latency_ms: float
    retrieval: dict = field(default_factory=dict)


class RAGPipeline:
    def __init__(self, settings: Settings, retriever: HybridRetriever, provider: LLMProvider) -> None:
        self.settings = settings
        self.retriever = retriever
        self.provider = provider

    def _query(self, question: str, history: list[str], triage: emergency.EmergencyAssessment) -> str:
        recent = " ".join(history[-2:]) if len(question.split()) < 8 and history else ""
        return " ".join(part for part in (recent, question, triage.retrieval_hint) if part)

    def _retrieve(self, question: str, history: list[str], triage: emergency.EmergencyAssessment,
                  filters: dict | None) -> tuple[list[RetrievedChunk], RetrievalTrace, int]:
        chunks, trace = self.retriever.retrieve(self._query(question, history, triage), filters=filters)
        chunks, dropped = scope.strip_injected(chunks)
        return chunks, trace, dropped

    def _gate(self, chunks: list[RetrievedChunk]) -> bool:
        return bool(chunks) and chunks[0].final_score >= self.settings.min_evidence_score

    def _audit(self, result: AnswerResult, question: str) -> None:
        record = {
            "request_id": result.request_id,
            "question_sha256": hashlib.sha256(question.encode()).hexdigest(),
            "sources": [s.url for s in result.sources],
            "abstained": result.abstained,
            "grounded": result.grounded,
            "coverage": result.citation_coverage,
            "unsupported_numbers": result.unsupported_numbers,
            "emergency": bool(result.emergency_banner),
            "provider": result.provider,
            "latency_ms": result.latency_ms,
            "ts": time.time(),
        }
        path = self.settings.data_dir / "audit" / "answers.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")

    def _finalise(self, request_id: str, raw_answer: str, chunks: list[RetrievedChunk], triage, redaction,
                  provider: LLMProvider, model: str, started: float, trace: RetrievalTrace) -> AnswerResult:
        report: CitationReport = validate(raw_answer, chunks)
        answer = report.text
        if report.unsupported_numbers and not report.abstained:
            answer += ("\n\n> Safety check: the following figures could not be matched to a cited source and "
                       f"must be verified before use: {', '.join(report.unsupported_numbers)}.")
        sources = [SourceView.from_retrieved(i, c) for i, c in enumerate(chunks, start=1)]
        result = AnswerResult(
            request_id=request_id, answer=answer, sources=sources, emergency_banner=triage.banner,
            abstained=report.abstained, out_of_scope=False, grounded=report.grounded,
            citation_coverage=report.coverage, unsupported_numbers=report.unsupported_numbers,
            redactions=redaction.found, provider=provider.name, model=model,
            latency_ms=round((time.perf_counter() - started) * 1000, 1), retrieval=asdict(trace),
        )
        metrics.observe_answer(result)
        return result

    async def answer(self, question: str, history: list[str] | None = None, filters: dict | None = None,
                     patient_context: str | None = None) -> AnswerResult:
        started, request_id, history = time.perf_counter(), str(uuid.uuid4()), history or []
        redaction = pii.redact(question)
        clean_question = redaction.text
        clean_context = pii.redact(patient_context).text if patient_context else None
        triage = emergency.assess(clean_question)

        if not triage.is_emergency and not scope.in_scope(clean_question, history):
            return AnswerResult(request_id, scope.OUT_OF_SCOPE_MESSAGE, [], None, False, True, True, 1.0, [],
                                redaction.found, "none", "none", round((time.perf_counter() - started) * 1000, 1))

        chunks, trace, _ = self._retrieve(clean_question, history, triage, filters)
        if not self._gate(chunks):
            result = AnswerResult(request_id, ABSTAIN_MESSAGE, [], triage.banner, True, False, False, 0.0, [],
                                  redaction.found, "none", "none", round((time.perf_counter() - started) * 1000, 1),
                                  asdict(trace))
            self._audit(result, clean_question)
            return result

        provider = self.provider
        messages = [LLMMessage("user", build_user_prompt(clean_question, chunks, clean_context))]
        try:
            response = await provider.complete(SYSTEM_PROMPT, messages, temperature=self.settings.llm_temperature,
                                               max_tokens=self.settings.llm_max_tokens)
        except LLMUnavailableError:
            log.warning("llm_unavailable_falling_back_to_extractive")
            provider = ExtractiveProvider()
            response = await provider.complete(SYSTEM_PROMPT, messages, temperature=0, max_tokens=800)

        result = self._finalise(request_id, response.text, chunks, triage, redaction, provider,
                                response.model, started, trace)
        self._audit(result, clean_question)
        return result

    async def stream(self, question: str, history: list[str] | None = None, filters: dict | None = None,
                     patient_context: str | None = None) -> AsyncIterator[dict]:
        """Yield events: meta, emergency, sources, token..., final."""
        started, request_id, history = time.perf_counter(), str(uuid.uuid4()), history or []
        redaction = pii.redact(question)
        clean_question = redaction.text
        triage = emergency.assess(clean_question)
        yield {"event": "meta", "data": {"request_id": request_id, "redactions": redaction.found}}
        if triage.is_emergency:
            yield {"event": "emergency", "data": {"banner": triage.banner, "codes": [r.code for r in triage.rules]}}

        if not triage.is_emergency and not scope.in_scope(clean_question, history):
            yield {"event": "final", "data": {"answer": scope.OUT_OF_SCOPE_MESSAGE, "out_of_scope": True}}
            return

        chunks, trace, _ = self._retrieve(clean_question, history, triage, filters)
        views = [asdict(SourceView.from_retrieved(i, c)) for i, c in enumerate(chunks, start=1)]
        yield {"event": "sources", "data": {"sources": views, "retrieval": asdict(trace)}}
        if not self._gate(chunks):
            yield {"event": "final", "data": {"answer": ABSTAIN_MESSAGE, "abstained": True}}
            return

        clean_context = pii.redact(patient_context).text if patient_context else None
        messages = [LLMMessage("user", build_user_prompt(clean_question, chunks, clean_context))]
        buffer: list[str] = []
        provider = self.provider
        try:
            iterator = provider.stream(SYSTEM_PROMPT, messages, temperature=self.settings.llm_temperature,
                                       max_tokens=self.settings.llm_max_tokens)
            async for token in iterator:
                buffer.append(token)
                yield {"event": "token", "data": {"text": token}}
        except LLMUnavailableError:
            provider = ExtractiveProvider()
            async for token in provider.stream(SYSTEM_PROMPT, messages, temperature=0, max_tokens=800):
                buffer.append(token)
                yield {"event": "token", "data": {"text": token}}

        result = self._finalise(request_id, "".join(buffer), chunks, triage, redaction, provider,
                                getattr(provider, "model", provider.name), started, trace)
        self._audit(result, clean_question)
        yield {"event": "final", "data": {
            "answer": result.answer, "abstained": result.abstained, "grounded": result.grounded,
            "citation_coverage": result.citation_coverage, "unsupported_numbers": result.unsupported_numbers,
            "latency_ms": result.latency_ms, "provider": result.provider,
        }}
