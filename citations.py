"""Citation enforcement and groundedness checks.

After generation every answer passes through `validate`, which:
  * removes citations that point at ids not supplied to the model,
  * measures citation coverage (share of factual sentences carrying a citation),
  * checks that every number with a clinical unit in the answer also appears in
    at least one cited source (a cheap but very effective dose hallucination
    detector),
  * decides whether the answer is safe to show, or must be replaced by an
    abstention message.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.app.domain import RetrievedChunk

_CITATION = re.compile(r"\[(\d{1,2})\]")
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
_CLINICAL_NUMBER = re.compile(
    r"\b(\d+(?:[.,]\d+)?)\s?(mg|g|ml|mL|micrograms?|ppm|%|months?|days?|hours?|years?)\b", re.IGNORECASE)
_NON_FACTUAL = re.compile(r"^(clinical judgement:|\*\*|#|summary)", re.IGNORECASE)

ABSTAIN_MESSAGE = (
    "I could not find enough evidence in the Root Canon knowledge base to answer this safely. "
    "Please consult the current BNF, SDCEP guidance or NICE directly, or rephrase the question with more "
    "clinical detail."
)


@dataclass
class CitationReport:
    text: str
    cited_ids: list[int] = field(default_factory=list)
    invalid_ids: list[int] = field(default_factory=list)
    coverage: float = 0.0
    unsupported_numbers: list[str] = field(default_factory=list)
    abstained: bool = False

    @property
    def grounded(self) -> bool:
        return not self.abstained and not self.unsupported_numbers and self.coverage >= 0.6


def _normalise_number(value: str, unit: str) -> str:
    unit = unit.lower().rstrip("s")
    unit = {"ml": "ml", "microgram": "microgram"}.get(unit, unit)
    return f"{value.replace(',', '')}{unit}"


def validate(answer: str, sources: list[RetrievedChunk]) -> CitationReport:
    stripped = answer.strip()
    if not stripped or stripped.startswith("INSUFFICIENT_EVIDENCE"):
        return CitationReport(text=ABSTAIN_MESSAGE, abstained=True)

    valid_ids = set(range(1, len(sources) + 1))
    invalid: list[int] = []

    def fix(match: re.Match[str]) -> str:
        cid = int(match.group(1))
        if cid in valid_ids:
            return match.group(0)
        invalid.append(cid)
        return ""

    text = _CITATION.sub(fix, stripped)
    cited = sorted({int(m) for m in _CITATION.findall(text)})

    sentences = [s.strip() for s in _SENTENCE.split(text) if len(s.strip()) > 25]
    factual = [s for s in sentences if not _NON_FACTUAL.match(s.lstrip("*- "))]
    covered = [s for s in factual if _CITATION.search(s)]
    coverage = len(covered) / len(factual) if factual else 1.0

    cited_text = " ".join(sources[i - 1].chunk.text for i in cited) if cited else ""
    source_numbers = {_normalise_number(v, u) for v, u in _CLINICAL_NUMBER.findall(cited_text)}
    unsupported = sorted({
        f"{v} {u}" for v, u in _CLINICAL_NUMBER.findall(text) if _normalise_number(v, u) not in source_numbers
    })
    return CitationReport(text=text, cited_ids=cited, invalid_ids=invalid, coverage=round(coverage, 3),
                          unsupported_numbers=unsupported)
