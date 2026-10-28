"""Claim level faithfulness.

Citation coverage proves that a sentence points at a source; it does not prove
the source says what the sentence says. This module checks that second
property in two ways:

`lexical_faithfulness` (always on, deterministic, no model call)
    Each cited sentence is reduced to its content terms with the clinical
    tokenizer. A sentence is supported when enough of those terms, weighted
    towards drugs, numbers and rare words, occur in the passages it cites.
    It is cheap enough to run on every answer and catches the common failure
    of a correct citation attached to an embellished claim.

`LLMJudge` (opt in, used by the live evaluation)
    Asks a model to label each cited sentence as supported, partially
    supported or unsupported by its cited passages, returning strict JSON. The
    verdicts are combined with the lexical score in the evaluation report.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import ClassVar

from backend.app.domain import RetrievedChunk
from backend.app.llm.base import LLMMessage, LLMProvider
from backend.app.retrieval.bm25 import tokenize

_CITATION = re.compile(r"\[(\d{1,2})\]")
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
_NUMERIC = re.compile(r"\d")
# Words that carry no clinical claim on their own.
_FILLER = frozenset([
    "also", "any", "been", "but", "each", "either", "further", "given", "into", "may", "might", "more", "most",
    "must", "need", "needs", "not", "only", "other", "over", "such", "than", "then", "there", "these", "they",
    "those", "through", "under", "used", "using", "very", "where", "whether", "while", "who", "whom", "would",
    "your", "their", "them", "our", "out", "one", "two", "per", "should", "could", "within", "without", "about",
    "after", "before", "between", "both",
])

SUPPORT_THRESHOLD = 0.6


@dataclass
class ClaimCheck:
    sentence: str
    cited: list[int]
    support: float
    supported: bool
    missing_terms: list[str] = field(default_factory=list)


@dataclass
class FaithfulnessReport:
    score: float
    claims: list[ClaimCheck] = field(default_factory=list)

    @property
    def unsupported(self) -> list[str]:
        return [c.sentence for c in self.claims if not c.supported]


def _content_terms(text: str) -> list[str]:
    terms = []
    for token in tokenize(_CITATION.sub("", text)):
        if token in _FILLER or (len(token) < 3 and not _NUMERIC.search(token)):
            continue
        terms.append(token)
    return list(dict.fromkeys(terms))


def _weight(term: str) -> float:
    # Numbers and long specific words decide clinical meaning; weight them more.
    if _NUMERIC.search(term):
        return 3.0
    return 1.5 if len(term) >= 8 else 1.0


def lexical_faithfulness(answer: str, sources: list[RetrievedChunk],
                         threshold: float = SUPPORT_THRESHOLD) -> FaithfulnessReport:
    claims: list[ClaimCheck] = []
    source_terms = {i: set(tokenize(f"{s.chunk.title} {s.chunk.section or ''} {s.chunk.text}"))
                    for i, s in enumerate(sources, start=1)}
    for sentence in (s.strip() for s in _SENTENCE.split(answer)):
        ids = sorted({int(m) for m in _CITATION.findall(sentence) if 1 <= int(m) <= len(sources)})
        if not ids:
            continue
        terms = _content_terms(sentence)
        if not terms:
            continue
        pool = set().union(*(source_terms[i] for i in ids))
        total = sum(_weight(t) for t in terms)
        found = sum(_weight(t) for t in terms if t in pool)
        support = found / total if total else 1.0
        missing = [t for t in terms if t not in pool]
        claims.append(ClaimCheck(sentence[:400], ids, round(support, 3), support >= threshold, missing[:8]))
    score = sum(c.support >= threshold for c in claims) / len(claims) if claims else 1.0
    return FaithfulnessReport(round(score, 3), claims)


JUDGE_SYSTEM = """You are a strict clinical fact checker. For each numbered claim, decide whether the cited \
passages fully support it. Use only the passages. Reply with JSON only, in the form \
{"verdicts": [{"claim": 1, "label": "supported" | "partial" | "unsupported", "reason": "short reason"}]}."""


@dataclass
class JudgeVerdict:
    claim: int
    label: str
    reason: str = ""


class LLMJudge:
    """Model graded faithfulness, used by `evaluation.run_eval --judge`."""

    SCORES: ClassVar[dict[str, float]] = {"supported": 1.0, "partial": 0.5, "unsupported": 0.0}

    def __init__(self, provider: LLMProvider, max_tokens: int = 800) -> None:
        self.provider = provider
        self.max_tokens = max_tokens

    def _prompt(self, report: FaithfulnessReport, sources: list[RetrievedChunk]) -> str:
        passages = "\n".join(f'<passage id="{i}">{s.chunk.text}</passage>' for i, s in enumerate(sources, start=1))
        claims = "\n".join(f'<claim n="{n}" cites="{",".join(map(str, c.cited))}">{c.sentence}</claim>'
                           for n, c in enumerate(report.claims, start=1))
        return f"<passages>\n{passages}\n</passages>\n<claims>\n{claims}\n</claims>"

    @staticmethod
    def parse(text: str) -> list[JudgeVerdict]:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return []
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return []
        verdicts = []
        for item in payload.get("verdicts", []):
            label = str(item.get("label", "")).lower()
            if label in LLMJudge.SCORES:
                verdicts.append(JudgeVerdict(int(item.get("claim", 0)), label, str(item.get("reason", ""))[:200]))
        return verdicts

    async def judge(self, answer: str, sources: list[RetrievedChunk]) -> tuple[float | None, list[JudgeVerdict]]:
        report = lexical_faithfulness(answer, sources)
        if not report.claims:
            return None, []
        response = await self.provider.complete(
            JUDGE_SYSTEM, [LLMMessage("user", self._prompt(report, sources))], temperature=0.0,
            max_tokens=self.max_tokens)
        verdicts = self.parse(response.text)
        if not verdicts:
            return None, []
        return round(sum(self.SCORES[v.label] for v in verdicts) / len(verdicts), 3), verdicts
