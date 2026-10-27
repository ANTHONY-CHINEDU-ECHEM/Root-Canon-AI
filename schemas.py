"""Request and response contracts for the public API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SearchFilters(BaseModel):
    source_type: list[str] | None = Field(default=None, description="e.g. ['uk_guideline', 'systematic_review']")
    jurisdiction: list[str] | None = None
    min_evidence_level: int | None = Field(default=None, ge=0, le=6)

    def to_store_filters(self) -> dict | None:
        filters = {k: v for k, v in self.model_dump().items() if v is not None}
        return filters or None


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    history: list[str] = Field(default_factory=list, max_length=12)
    patient_context: str | None = Field(default=None, max_length=1500,
                                        description="Optional, de identified: age band, medical history, medications")
    filters: SearchFilters | None = None
    provider: Literal["anthropic", "openai", "ollama"] | None = None


class SourceOut(BaseModel):
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


class AskResponse(BaseModel):
    request_id: str
    answer: str
    sources: list[SourceOut]
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


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=500)
    top_k: int = Field(default=10, ge=1, le=50)
    filters: SearchFilters | None = None


class RegimenRequest(BaseModel):
    drug: str
    age_years: float | None = Field(default=None, ge=0, le=120)


class LocalAnaestheticRequest(BaseModel):
    product: str
    weight_kg: float = Field(..., ge=3, le=250)


class InteractionRequest(BaseModel):
    drugs: list[str] = Field(..., min_length=2, max_length=20)
