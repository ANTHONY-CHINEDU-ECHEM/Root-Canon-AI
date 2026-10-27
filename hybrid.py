"""Hybrid retrieval: dense + BM25, fused with Reciprocal Rank Fusion, then
re-scored with clinical priors and reranked.

Final score
    final = rerank * (1 - w_e - w_r) + w_e * evidence_prior + w_r * recency + uk_bonus

where evidence_prior favours national guidance and systematic reviews and
recency decays with a configurable half life. A per document cap keeps one
long guideline from crowding every slot in the context window.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from datetime import date

from backend.app.config import Settings
from backend.app.domain import Chunk, RetrievedChunk
from backend.app.retrieval.bm25 import BM25Index
from backend.app.retrieval.embedder import Embedder
from backend.app.retrieval.reranker import Reranker
from backend.app.retrieval.vector_store import VectorStore
from ingestion.processing.evidence import evidence_prior

UK_BONUS = 0.05
RECENCY_WEIGHT = 0.05
MAX_CHUNKS_PER_DOC = 2


def reciprocal_rank_fusion(rankings: list[list[str]], k: int = 60) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item_id in enumerate(ranking, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    return scores


def recency_score(year: int | None, half_life: float, today: int | None = None) -> float:
    if not year:
        return 0.3
    age = max(0, (today or date.today().year) - year)
    return math.pow(0.5, age / half_life)


@dataclass
class RetrievalTrace:
    dense_ms: float = 0.0
    sparse_ms: float = 0.0
    rerank_ms: float = 0.0
    candidates: int = 0
    returned: int = 0
    filters: dict = field(default_factory=dict)


class HybridRetriever:
    def __init__(self, settings: Settings, embedder: Embedder, store: VectorStore,
                 bm25: BM25Index, reranker: Reranker) -> None:
        self.settings = settings
        self.embedder = embedder
        self.store = store
        self.bm25 = bm25
        self.reranker = reranker

    def retrieve(self, query: str, top_k: int | None = None,
                 filters: dict | None = None) -> tuple[list[RetrievedChunk], RetrievalTrace]:
        s, trace = self.settings, RetrievalTrace(filters=filters or {})
        top_k = top_k or s.top_k_final

        started = time.perf_counter()
        dense_hits = self.store.search(self.embedder.embed_query(query), s.top_k_dense, filters)
        trace.dense_ms = (time.perf_counter() - started) * 1000

        started = time.perf_counter()
        sparse_hits = self.bm25.search(query, s.top_k_sparse * 2)
        trace.sparse_ms = (time.perf_counter() - started) * 1000

        by_id: dict[str, Chunk] = {c.chunk_id: c for c, _ in dense_hits}
        missing = [cid for cid, _ in sparse_hits if cid not in by_id]
        for chunk in self.store.get(missing):
            by_id[chunk.chunk_id] = chunk
        from backend.app.retrieval.vector_store import _matches  # local import avoids a cycle
        sparse_hits = [(cid, sc) for cid, sc in sparse_hits if cid in by_id and _matches(by_id[cid], filters)]
        sparse_hits = sparse_hits[: s.top_k_sparse]

        fused = reciprocal_rank_fusion([[c.chunk_id for c, _ in dense_hits], [cid for cid, _ in sparse_hits]], s.rrf_k)
        max_fused = max(fused.values(), default=1.0)
        dense_map = {c.chunk_id: sc for c, sc in dense_hits}
        sparse_map = dict(sparse_hits)
        candidates = [
            RetrievedChunk(chunk=by_id[cid], dense_score=dense_map.get(cid, 0.0),
                           sparse_score=sparse_map.get(cid, 0.0), fused_score=score / max_fused)
            for cid, score in sorted(fused.items(), key=lambda kv: -kv[1])[: max(top_k * 4, 24)]
        ]
        trace.candidates = len(candidates)

        started = time.perf_counter()
        reranked = self.reranker.rerank(query, candidates)
        trace.rerank_ms = (time.perf_counter() - started) * 1000

        w_e, w_r = s.evidence_weight, RECENCY_WEIGHT
        for item in reranked:
            base = item.rerank_score if item.rerank_score is not None else item.fused_score
            item.final_score = (
                base * (1 - w_e - w_r)
                + w_e * evidence_prior(item.chunk.evidence_level)
                + w_r * recency_score(item.chunk.published_year, s.recency_half_life_years)
                + (UK_BONUS if item.chunk.jurisdiction == "UK" else 0.0)
            )
        reranked.sort(key=lambda c: -c.final_score)

        results, per_doc = [], {}
        for item in reranked:
            if per_doc.get(item.chunk.doc_id, 0) >= MAX_CHUNKS_PER_DOC:
                continue
            per_doc[item.chunk.doc_id] = per_doc.get(item.chunk.doc_id, 0) + 1
            results.append(item)
            if len(results) >= top_k:
                break
        trace.returned = len(results)
        return results, trace
