"""Second stage reranking.

A cross encoder reads the query and each candidate together, which corrects
the most common hybrid retrieval failure: a chunk that shares vocabulary with
the question but answers a different question (for example, amoxicillin for
endocarditis prophylaxis versus amoxicillin for a dental abscess).
"""

from __future__ import annotations

import abc
import math
from functools import lru_cache

from backend.app.domain import RetrievedChunk
from backend.app.retrieval.bm25 import tokenize


class Reranker(abc.ABC):
    @abc.abstractmethod
    def rerank(self, query: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]: ...


class LexicalOverlapReranker(Reranker):
    """Lightweight fallback: query term coverage blended with the fused score."""

    def rerank(self, query: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
        query_terms = set(tokenize(query))
        for item in candidates:
            chunk_terms = set(tokenize(item.chunk.title + " " + item.chunk.text))
            coverage = len(query_terms & chunk_terms) / (len(query_terms) or 1)
            item.rerank_score = 0.6 * coverage + 0.4 * item.fused_score
        return sorted(candidates, key=lambda c: -(c.rerank_score or 0.0))


class CrossEncoderReranker(Reranker):
    def __init__(self, model_name: str) -> None:
        from sentence_transformers import CrossEncoder

        self.model = CrossEncoder(model_name, max_length=512)

    def rerank(self, query: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
        if not candidates:
            return []
        pairs = [(query, f"{c.chunk.title}. {c.chunk.text}") for c in candidates]
        logits = self.model.predict(pairs, batch_size=32)
        for item, logit in zip(candidates, logits, strict=True):
            item.rerank_score = 1.0 / (1.0 + math.exp(-float(logit)))
        return sorted(candidates, key=lambda c: -(c.rerank_score or 0.0))


@lru_cache(maxsize=1)
def build_reranker(backend: str, model_name: str) -> Reranker:
    if backend == "cross_encoder":
        try:
            return CrossEncoderReranker(model_name)
        except ImportError:
            return LexicalOverlapReranker()
    return LexicalOverlapReranker()
