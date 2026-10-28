"""The Root Canon question answering pipeline.

    question
      -> PII redaction            (nothing identifiable leaves the service)
      -> emergency triage         (action banner returned immediately)
      -> scope check              (non dental questions declined, no LLM call)
      -> query understanding      (UK spelling, generic names, age, weight, intents)
      -> deterministic tools      (regimens, LA ceilings, adrenaline, safety screen)
      -> query building           (history aware, emergency hints, generic expansion)
      -> hybrid retrieval         (dense + BM25 + RRF + rerank + clinical priors + supersession)
      -> injection filter         (untrusted chunks dropped)
      -> evidence gate            (abstain if the best evidence is too weak)
      -> generation               (provider router: primary, fallbacks, extractive safety net)
      -> citation validation      (invalid ids removed, numbers checked)
      -> faithfulness check       (each cited claim compared with its cited passages)
      -> audit record             (keyed hash of the question, sources, scores, latency)

The same pipeline powers the blocking /ask endpoint and the streaming /ask/stream
endpoint; the streaming path yields typed events the interface renders live:
meta, emergency, tools, sources, token..., final.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass, field

from backend.app.audit import AuditLog
from backend.app.clinical import entities as clinical_entities
from backend.app.clinical import router as tool_router
from backend.app.config import Settings
from backend.app.domain import RetrievedChunk
from backend.app.generation.answerability import query_coverage
from backend.app.generation.citations import ABSTAIN_MESSAGE, CitationReport, validate
from backend.app.generation.faithfulness import lexical_faithfulness
from backend.app.generation.prompts import SYSTEM_PROMPT, build_user_prompt
from backend.app.guardrails import emergency, pii, scope
from backend.app.llm.base import LLMMessage, LLMProvider, LLMUnavailableError
from backend.app.llm.factory import ExtractiveProvider
from backend.app.logging_setup import get_logger
from backend.app.observability import metrics
from backend.app.retrieval.hybrid import HybridRetriever, RetrievalTrace
from ingestion.processing.evidence import EVIDENCE_LABELS

log = get_logger("rag")

INTERRUPTED_NOTE = ("\n\n> The model stopped before finishing. The text above has been checked, but the answer "
                    "may be incomplete; ask again for the full answer.")


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
    superseded_by: dict | None = None

    @classmethod
    def from_retrieved(cls, index: int, item: RetrievedChunk) -> SourceView:
        c = item.chunk
        return cls(index, c.title, c.url, c.section, c.source, c.source_type.value, EVIDENCE_LABELS[c.evidence_level],
                   int(c.evidence_level), c.published_year, c.jurisdiction, c.text[:600], round(item.final_score, 4),
                   item.superseded_by)


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
    faithfulness: float | None = None
    unsupported_claims: list[str] = field(default_factory=list)
    tool_cards: list[dict] = field(default_factory=list)
    entities: dict = field(default_factory=dict)


@dataclass
class _Prepared:
    request_id: str
    started: float
    question: str
    context: str | None
    history: list[str]
    redaction: pii.RedactionResult
    triage: emergency.EmergencyAssessment
    entities: clinical_entities.ClinicalEntities
    in_scope: bool
    tool_cards: list[dict]


class RAGPipeline:
    def __init__(self, settings: Settings, retriever: HybridRetriever, provider: LLMProvider,
                 audit: AuditLog | None = None) -> None:
        self.settings = settings
        self.retriever = retriever
        self.provider = provider
        self.audit = audit or AuditLog(settings.audit_dir, settings.audit_salt.get_secret_value())

    # ------------------------------------------------------------------ stages

    def _prepare(self, question: str, history: list[str] | None, patient_context: str | None) -> _Prepared:
        started, request_id, history = time.perf_counter(), str(uuid.uuid4()), list(history or [])
        redaction = pii.redact(question)
        clean_question = redaction.text
        clean_context = pii.redact(patient_context).text if patient_context else None
        clean_history = [pii.redact(turn).text for turn in history]
        triage = emergency.assess(clean_question)
        entities = clinical_entities.extract(clean_question)
        relevant = triage.is_emergency or scope.in_scope(entities.normalised, clean_history)
        cards: list[dict] = []
        if relevant and self.settings.tool_routing:
            is_anaphylaxis = any(rule.code == "anaphylaxis" for rule in triage.rules)
            cards = [card.as_dict() for card in tool_router.route(clean_question, clean_context, is_anaphylaxis)]
        return _Prepared(request_id, started, clean_question, clean_context, clean_history, redaction, triage,
                         entities, relevant, cards)

    def _query(self, prep: _Prepared) -> str:
        question = prep.entities.normalised if self.settings.query_expansion else prep.question
        recent = " ".join(prep.history[-2:]) if len(question.split()) < 8 and prep.history else ""
        expansion = prep.entities.expansion if self.settings.query_expansion else ""
        return " ".join(part for part in (recent, question, expansion, prep.triage.retrieval_hint) if part)

    def _retrieve(self, prep: _Prepared, filters: dict | None) -> tuple[list[RetrievedChunk], RetrievalTrace]:
        chunks, trace = self.retriever.retrieve(self._query(prep), filters=filters)
        chunks, dropped = scope.strip_injected(chunks)
        if dropped:
            log.warning("injected_chunks_dropped", count=dropped)
        metrics.observe_retrieval(trace)
        return chunks, trace

    def _gate(self, prep: _Prepared, chunks: list[RetrievedChunk], trace: RetrievalTrace) -> bool:
        if not chunks or chunks[0].final_score < self.settings.min_evidence_score:
            return False
        if prep.triage.is_emergency:
            return True
        answerability = query_coverage(prep.entities.normalised, chunks, self.retriever.bm25)
        trace.query_coverage = answerability.coverage
        return answerability.coverage >= self.settings.min_query_coverage

    def _elapsed(self, prep: _Prepared) -> float:
        return round((time.perf_counter() - prep.started) * 1000, 1)

    def _messages(self, prep: _Prepared, chunks: list[RetrievedChunk]) -> list[LLMMessage]:
        return [LLMMessage("user", build_user_prompt(prep.question, chunks, prep.context, prep.entities.normalised))]

    def _provider_used(self, provider: LLMProvider) -> LLMProvider:
        return getattr(provider, "last_used", provider)

    def _out_of_scope(self, prep: _Prepared) -> AnswerResult:
        return AnswerResult(prep.request_id, scope.OUT_OF_SCOPE_MESSAGE, [], None, False, True, True, 1.0, [],
                            prep.redaction.found, "none", "none", self._elapsed(prep), entities=prep.entities.as_dict())

    def _abstain(self, prep: _Prepared, trace: RetrievalTrace) -> AnswerResult:
        return AnswerResult(prep.request_id, ABSTAIN_MESSAGE, [], prep.triage.banner, True, False, False, 0.0, [],
                            prep.redaction.found, "none", "none", self._elapsed(prep), asdict(trace),
                            tool_cards=prep.tool_cards, entities=prep.entities.as_dict())

    def _finalise(self, prep: _Prepared, raw_answer: str, chunks: list[RetrievedChunk], provider: LLMProvider,
                  model: str, trace: RetrievalTrace, interrupted: bool = False) -> AnswerResult:
        report: CitationReport = validate(raw_answer, chunks)
        answer = report.text
        faith = None if report.abstained else lexical_faithfulness(answer, chunks)
        if report.unsupported_numbers and not report.abstained:
            answer += ("\n\n> Safety check: the following figures could not be matched to a cited source and "
                       f"must be verified before use: {', '.join(report.unsupported_numbers)}.")
        superseded_cited = [chunks[i - 1] for i in report.cited_ids if chunks[i - 1].superseded_by]
        if superseded_cited and not report.abstained:
            newest = superseded_cited[0].superseded_by or {}
            answer += (f"\n\n> Currency check: this answer cites guidance that has been superseded. Check the "
                       f"current version: {newest.get('title', 'see the source panel')}.")
        if interrupted and not report.abstained:
            answer += INTERRUPTED_NOTE
        grounded = report.grounded and (faith is None or faith.score >= self.settings.min_faithfulness)
        sources = [SourceView.from_retrieved(i, c) for i, c in enumerate(chunks, start=1)]
        result = AnswerResult(
            request_id=prep.request_id, answer=answer, sources=sources, emergency_banner=prep.triage.banner,
            abstained=report.abstained, out_of_scope=False, grounded=grounded and not interrupted,
            citation_coverage=report.coverage, unsupported_numbers=report.unsupported_numbers,
            redactions=prep.redaction.found, provider=provider.name, model=model,
            latency_ms=self._elapsed(prep), retrieval=asdict(trace),
            faithfulness=faith.score if faith else None, unsupported_claims=faith.unsupported if faith else [],
            tool_cards=prep.tool_cards, entities=prep.entities.as_dict(),
        )
        metrics.observe_answer(result)
        return result

    def _record(self, result: AnswerResult, prep: _Prepared) -> None:
        try:
            self.audit.record_answer(result, prep.question)
        except OSError as exc:  # the audit log must never block a clinical answer
            log.error("audit_write_failed", error=str(exc))

    # -------------------------------------------------------------- public API

    async def answer(self, question: str, history: list[str] | None = None, filters: dict | None = None,
                     patient_context: str | None = None) -> AnswerResult:
        prep = self._prepare(question, history, patient_context)
        if not prep.in_scope:
            result = self._out_of_scope(prep)
            metrics.observe_answer(result)
            return result

        chunks, trace = self._retrieve(prep, filters)
        if not self._gate(prep, chunks, trace):
            result = self._abstain(prep, trace)
            metrics.observe_answer(result)
            self._record(result, prep)
            return result

        provider: LLMProvider = self.provider
        messages = self._messages(prep, chunks)
        try:
            response = await provider.complete(SYSTEM_PROMPT, messages, temperature=self.settings.llm_temperature,
                                               max_tokens=self.settings.llm_max_tokens)
            provider = self._provider_used(provider)
        except LLMUnavailableError:
            log.warning("llm_unavailable_falling_back_to_extractive")
            provider = ExtractiveProvider()
            response = await provider.complete(SYSTEM_PROMPT, messages, temperature=0, max_tokens=800)

        result = self._finalise(prep, response.text, chunks, provider, response.model, trace)
        self._record(result, prep)
        return result

    async def stream(self, question: str, history: list[str] | None = None, filters: dict | None = None,
                     patient_context: str | None = None) -> AsyncIterator[dict]:
        """Yield events: meta, emergency, tools, sources, token..., final."""
        prep = self._prepare(question, history, patient_context)
        yield {"event": "meta", "data": {"request_id": prep.request_id, "redactions": prep.redaction.found,
                                         "entities": prep.entities.as_dict()}}
        if prep.triage.is_emergency:
            yield {"event": "emergency", "data": {"banner": prep.triage.banner,
                                                  "codes": [r.code for r in prep.triage.rules]}}
        if not prep.in_scope:
            result = self._out_of_scope(prep)
            metrics.observe_answer(result)
            yield {"event": "final", "data": {"answer": result.answer, "out_of_scope": True,
                                              "request_id": prep.request_id}}
            return
        if prep.tool_cards:
            yield {"event": "tools", "data": {"cards": prep.tool_cards}}

        chunks, trace = self._retrieve(prep, filters)
        passed = self._gate(prep, chunks, trace)  # before the sources event, so the trace carries coverage
        views = [asdict(SourceView.from_retrieved(i, c)) for i, c in enumerate(chunks, start=1)]
        yield {"event": "sources", "data": {"sources": views, "retrieval": asdict(trace)}}
        if not passed:
            result = self._abstain(prep, trace)
            metrics.observe_answer(result)
            self._record(result, prep)
            yield {"event": "final", "data": {"answer": ABSTAIN_MESSAGE, "abstained": True,
                                              "request_id": prep.request_id}}
            return

        messages = self._messages(prep, chunks)
        buffer: list[str] = []
        provider: LLMProvider = self.provider
        interrupted = False
        try:
            async for token in provider.stream(SYSTEM_PROMPT, messages, temperature=self.settings.llm_temperature,
                                               max_tokens=self.settings.llm_max_tokens):
                buffer.append(token)
                yield {"event": "token", "data": {"text": token}}
            provider = self._provider_used(provider)
        except LLMUnavailableError:
            if buffer:
                interrupted = True
                provider = self._provider_used(provider)
            else:
                provider = ExtractiveProvider()
                async for token in provider.stream(SYSTEM_PROMPT, messages, temperature=0, max_tokens=800):
                    buffer.append(token)
                    yield {"event": "token", "data": {"text": token}}

        result = self._finalise(prep, "".join(buffer), chunks, provider, getattr(provider, "model", provider.name),
                                trace, interrupted)
        self._record(result, prep)
        yield {"event": "final", "data": {
            "request_id": result.request_id, "answer": result.answer, "abstained": result.abstained,
            "grounded": result.grounded, "citation_coverage": result.citation_coverage,
            "faithfulness": result.faithfulness, "unsupported_numbers": result.unsupported_numbers,
            "unsupported_claims": result.unsupported_claims, "latency_ms": result.latency_ms,
            "provider": result.provider, "model": result.model,
        }}
