"""Evaluation harness.

Metrics
  retrieval_hit_at_k    expected document appears in the top k sources
  retrieval_mrr         mean reciprocal rank of the expected document
  fact_recall           share of expected facts present in the answer text
  citation_coverage     share of factual sentences with a valid citation
  unsupported_rate      share of answers containing a figure not found in cited sources
  abstention_accuracy   correct abstain or answer decision on the abstention subset
  triage_accuracy       emergency flag matches the label
  p50 and p95 latency

Usage
  python -m evaluation.run_eval                      # offline: seed index, extractive generator
  python -m evaluation.run_eval --provider anthropic # live: uses the configured index and Claude
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
from pathlib import Path

from backend.app.config import Settings, get_settings
from backend.app.generation.rag_pipeline import RAGPipeline
from backend.app.llm.factory import build_provider
from backend.app.retrieval.bm25 import BM25Index
from backend.app.retrieval.embedder import HashingEmbedder
from backend.app.retrieval.hybrid import HybridRetriever
from backend.app.retrieval.reranker import LexicalOverlapReranker
from backend.app.retrieval.vector_store import InMemoryVectorStore
from ingestion.processing.chunker import chunk_document, contextualise
from ingestion.seed import seed_documents

GOLDEN = Path(__file__).with_name("golden_set.jsonl")


def offline_pipeline(settings: Settings) -> RAGPipeline:
    chunks = [c for d in seed_documents() for c in chunk_document(d)]
    embedder = HashingEmbedder(settings.embedding_dim)
    store = InMemoryVectorStore(embedder.dim)
    store.upsert(chunks, embedder.embed_documents([contextualise(c) for c in chunks]))
    bm25 = BM25Index().build([c.chunk_id for c in chunks], [f"{c.title} {c.section} {c.text}" for c in chunks])
    retriever = HybridRetriever(settings, embedder, store, bm25, LexicalOverlapReranker())
    return RAGPipeline(settings, retriever, build_provider(settings, "extractive"))


async def evaluate(pipeline: RAGPipeline, k: int = 5) -> dict:
    rows = [json.loads(line) for line in GOLDEN.read_text().splitlines() if line.strip()]
    per_item, latencies = [], []
    for row in rows:
        result = await pipeline.answer(row["question"])
        latencies.append(result.latency_ms)
        doc_ids = [s.url for s in result.sources]
        expected_url = None
        if row["expected_doc"]:
            expected_url = next(d.url for d in seed_documents() if d.doc_id == row["expected_doc"])
        rank = doc_ids.index(expected_url) + 1 if expected_url in doc_ids else None
        answer = result.answer.lower()
        facts = row["expected_facts"]
        per_item.append({
            "id": row["id"],
            "category": row["category"],
            "hit": bool(rank and rank <= k) if expected_url else None,
            "rr": (1 / rank if rank else 0.0) if expected_url else None,
            "fact_recall": (sum(f.lower() in answer for f in facts) / len(facts)) if facts else None,
            "coverage": result.citation_coverage if not result.abstained else None,
            "unsupported": bool(result.unsupported_numbers),
            "abstain_ok": result.abstained == row["should_abstain"],
            "triage_ok": bool(result.emergency_banner) == row["emergency"],
        })

    def mean(key: str) -> float:
        values = [r[key] for r in per_item if r[key] is not None]
        return round(statistics.mean(float(v) for v in values), 3) if values else 0.0

    latencies.sort()
    return {
        "n": len(per_item),
        f"retrieval_hit_at_{k}": mean("hit"),
        "retrieval_mrr": mean("rr"),
        "fact_recall": mean("fact_recall"),
        "citation_coverage": mean("coverage"),
        "unsupported_rate": mean("unsupported"),
        "abstention_accuracy": mean("abstain_ok"),
        "triage_accuracy": mean("triage_ok"),
        "latency_ms_p50": latencies[len(latencies) // 2],
        "latency_ms_p95": latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))],
        "items": per_item,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default=None, choices=["anthropic", "openai", "ollama"])
    parser.add_argument("--out", type=Path, default=Path("evaluation/results/latest.json"))
    args = parser.parse_args()
    if args.provider:
        from backend.app.api.deps import build_container

        container = build_container(get_settings())
        pipeline = container.pipeline_for(args.provider)
    else:
        settings = Settings(env="test", embedding_backend="hashing", reranker_backend="none",
                            vector_backend="memory", redis_url=None, data_dir=Path("data/eval"),
                            min_evidence_score=0.1)
        pipeline = offline_pipeline(settings)
    report = asyncio.run(evaluate(pipeline))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "items"}, indent=2))


if __name__ == "__main__":
    main()
