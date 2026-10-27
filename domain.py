"""Core domain models shared by ingestion, retrieval and generation.

A SourceDocument is one authoritative record (a PubMed article, a NICE
guideline section, an openFDA label). Documents are split into Chunks, which
are the unit of retrieval and citation.
"""

from __future__ import annotations

from datetime import date
from enum import IntEnum, StrEnum

from pydantic import BaseModel, Field


class SourceType(StrEnum):
    UK_GUIDELINE = "uk_guideline"          # NICE, SDCEP, OHID, RCUK, FGDP
    SYSTEMATIC_REVIEW = "systematic_review"
    RANDOMISED_TRIAL = "randomised_trial"
    OBSERVATIONAL = "observational"
    CASE_REPORT = "case_report"
    NARRATIVE_REVIEW = "narrative_review"
    DRUG_LABEL = "drug_label"
    PATIENT_INFORMATION = "patient_information"
    OTHER = "other"


class EvidenceLevel(IntEnum):
    """Higher is stronger. Loosely follows the Oxford CEBM hierarchy, with UK
    national guidance placed at the top because it is the standard of care a UK
    dentist is measured against."""

    UNGRADED = 0
    EXPERT_OPINION = 1
    CASE_SERIES = 2
    OBSERVATIONAL = 3
    RANDOMISED_TRIAL = 4
    SYSTEMATIC_REVIEW = 5
    NATIONAL_GUIDANCE = 6


class Licence(StrEnum):
    OPEN_GOVERNMENT = "OGL-3.0"
    CC_BY = "CC-BY"
    CC_BY_NC = "CC-BY-NC"
    CC0 = "CC0"
    PUBLIC_DOMAIN_US_GOV = "US-Gov-PD"
    ABSTRACT_FAIR_DEALING = "abstract-fair-dealing"
    SYNDICATION_LICENSED = "syndication-licensed"
    UNKNOWN = "unknown"


class SourceDocument(BaseModel):
    doc_id: str = Field(..., description="Stable identifier, e.g. pubmed:31234567")
    source: str = Field(..., description="Connector name, e.g. pubmed, nice, openfda")
    source_type: SourceType
    title: str
    text: str
    url: str
    publisher: str | None = None
    journal: str | None = None
    authors: list[str] = Field(default_factory=list)
    published: date | None = None
    updated: date | None = None
    publication_types: list[str] = Field(default_factory=list)
    mesh_terms: list[str] = Field(default_factory=list)
    doi: str | None = None
    licence: Licence = Licence.UNKNOWN
    jurisdiction: str | None = None
    sections: list[tuple[str, str]] = Field(default_factory=list, description="(heading, body) pairs")
    extra: dict[str, str] = Field(default_factory=dict)


class Chunk(BaseModel):
    chunk_id: str
    doc_id: str
    text: str
    section: str | None = None
    title: str
    url: str
    source: str
    source_type: SourceType
    evidence_level: EvidenceLevel = EvidenceLevel.UNGRADED
    published_year: int | None = None
    jurisdiction: str | None = None
    licence: Licence = Licence.UNKNOWN
    token_count: int = 0
    position: int = 0

    def citation_label(self) -> str:
        year = f", {self.published_year}" if self.published_year else ""
        return f"{self.title}{year}"


class RetrievedChunk(BaseModel):
    chunk: Chunk
    dense_score: float = 0.0
    sparse_score: float = 0.0
    fused_score: float = 0.0
    rerank_score: float | None = None
    final_score: float = 0.0
