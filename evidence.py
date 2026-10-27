"""Evidence grading for retrieved documents.

The grade is used twice: as a small additive prior during ranking, and as a
visible badge in the interface so the clinician can see at a glance whether a
claim rests on national guidance, a systematic review, or a single case report.
"""

from __future__ import annotations

from backend.app.domain import EvidenceLevel, SourceDocument, SourceType

_BY_SOURCE_TYPE = {
    SourceType.UK_GUIDELINE: EvidenceLevel.NATIONAL_GUIDANCE,
    SourceType.SYSTEMATIC_REVIEW: EvidenceLevel.SYSTEMATIC_REVIEW,
    SourceType.RANDOMISED_TRIAL: EvidenceLevel.RANDOMISED_TRIAL,
    SourceType.OBSERVATIONAL: EvidenceLevel.OBSERVATIONAL,
    SourceType.CASE_REPORT: EvidenceLevel.CASE_SERIES,
    SourceType.NARRATIVE_REVIEW: EvidenceLevel.EXPERT_OPINION,
    SourceType.DRUG_LABEL: EvidenceLevel.OBSERVATIONAL,
    SourceType.PATIENT_INFORMATION: EvidenceLevel.EXPERT_OPINION,
    SourceType.OTHER: EvidenceLevel.UNGRADED,
}

EVIDENCE_LABELS = {
    EvidenceLevel.NATIONAL_GUIDANCE: "UK national guidance",
    EvidenceLevel.SYSTEMATIC_REVIEW: "Systematic review",
    EvidenceLevel.RANDOMISED_TRIAL: "Randomised trial",
    EvidenceLevel.OBSERVATIONAL: "Observational or regulatory",
    EvidenceLevel.CASE_SERIES: "Case report or series",
    EvidenceLevel.EXPERT_OPINION: "Expert opinion or review",
    EvidenceLevel.UNGRADED: "Ungraded",
}

_COCHRANE_HINTS = ("cochrane database syst rev", "cochrane database of systematic reviews")


def grade_evidence(document: SourceDocument) -> EvidenceLevel:
    level = _BY_SOURCE_TYPE.get(document.source_type, EvidenceLevel.UNGRADED)
    journal = (document.journal or "").lower()
    if any(h in journal for h in _COCHRANE_HINTS):
        level = max(level, EvidenceLevel.SYSTEMATIC_REVIEW)
    return level


def evidence_prior(level: EvidenceLevel) -> float:
    """Map a grade onto [0, 1] for use as a ranking prior."""
    return int(level) / int(EvidenceLevel.NATIONAL_GUIDANCE)
