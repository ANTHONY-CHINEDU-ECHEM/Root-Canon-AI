"""End to end ingestion pipeline.

    connectors  ->  clean  ->  deduplicate  ->  chunk  ->  embed  ->  index
                                                             \\-> BM25 build
                                                             \\-> manifest

Raw documents are written to data/raw/<source>.jsonl as they stream in, so a
crashed run can resume from disk with `--from-raw` without hitting the APIs
again. Every run produces a manifest with counts, licences and timings which is
committed alongside evaluation results for provenance.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

import yaml

from backend.app.config import Settings
from backend.app.domain import Chunk, SourceDocument
from backend.app.logging_setup import get_logger
from backend.app.retrieval.bm25 import BM25Index
from backend.app.retrieval.embedder import build_embedder
from backend.app.retrieval.supersession import default_graph
from backend.app.retrieval.vector_store import InMemoryVectorStore, QdrantVectorStore, VectorStore
from ingestion.processing.chunker import chunk_document, contextualise
from ingestion.processing.dedup import Deduplicator
from ingestion.sources import REGISTRY

log = get_logger("ingestion.pipeline")

# Ingest in licence priority order so the deduplicator keeps the best copy.
SOURCE_ORDER = ["nice", "sdcep", "govuk", "europepmc", "pubmed", "openfda", "medlineplus"]
EMBED_BATCH = 256


def load_corpus_config(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def connector_kwargs(source: str, config: dict) -> list[dict]:
    section = config.get(source, {})
    if source == "pubmed":
        base = section.get("base_filters", "")
        jobs = []
        for pt in section.get("priority_publication_types", []):
            for query in section.get("queries", {}).values():
                jobs.append({"term": f"({query['term']}) AND {pt} AND {base}"})
        for query in section.get("queries", {}).values():
            jobs.append({"term": f"({query['term']}) AND {base}"})
        return jobs
    if source == "europepmc":
        return [{"query": section["query"], "include_full_text": section.get("include_full_text", True)}]
    if source == "openfda":
        return [{"generic_names": section["generic_names"]}]
    if source == "medlineplus":
        return [{"topics": section["topics"]}]
    if source == "govuk":
        return [{"base_paths": section["base_paths"]}]
    if source == "nice":
        return [{"guidance_ids": section["guidance_ids"]}]
    if source == "sdcep":
        return [{"urls": section["urls"]}]
    raise KeyError(source)


async def harvest(sources: list[str], config: dict, raw_dir: Path, limit_per_job: int | None) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)  # noqa: ASYNC240 - one call before any network I/O
    for source in [s for s in SOURCE_ORDER if s in sources]:
        out = raw_dir / f"{source}.jsonl"
        seen_ids: set[str] = set()
        if out.exists():
            seen_ids = {json.loads(line)["doc_id"] for line in out.open(encoding="utf-8") if line.strip()}
        with out.open("a", encoding="utf-8") as handle:
            for kwargs in connector_kwargs(source, config):
                connector_cls = REGISTRY[source]
                async with connector_cls(**kwargs) as connector:
                    written = 0
                    async for document in connector.fetch(limit=limit_per_job):
                        if document.doc_id in seen_ids:
                            continue
                        seen_ids.add(document.doc_id)
                        handle.write(document.model_dump_json() + "\n")
                        written += 1
                    log.info("harvested", source=source, job=str(kwargs)[:120], written=written)


def iter_raw(raw_dir: Path, sources: list[str]) -> Iterable[SourceDocument]:
    for source in [s for s in SOURCE_ORDER if s in sources]:
        path = raw_dir / f"{source}.jsonl"
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    yield SourceDocument.model_validate_json(line)


def build_store(settings: Settings, dim: int) -> VectorStore:
    if settings.vector_backend == "qdrant":
        return QdrantVectorStore(settings.qdrant_url, settings.qdrant_collection, dim)
    return InMemoryVectorStore(dim)


def index_documents(settings: Settings, documents: Iterable[SourceDocument]) -> dict:
    started = time.perf_counter()
    embedder = build_embedder(settings.embedding_backend, settings.embedding_model, settings.embedding_dim)
    store = build_store(settings, embedder.dim)
    dedup = Deduplicator()
    graph = default_graph()
    stats: Counter[str] = Counter()
    licences: Counter[str] = Counter()
    bm25_ids: list[str] = []
    bm25_texts: list[str] = []
    batch: list[Chunk] = []

    def flush() -> None:
        if not batch:
            return
        vectors = embedder.embed_documents([contextualise(c) for c in batch])
        store.upsert(batch, vectors)
        stats["chunks"] += len(batch)
        batch.clear()

    for document in documents:
        stats["documents_seen"] += 1
        if dedup.add(document) is None:
            continue
        stats["documents_indexed"] += 1
        stats[f"source:{document.source}"] += 1
        licences[document.licence.value] += 1
        for chunk in chunk_document(document):
            if graph.find(chunk) is not None:
                stats["superseded_chunks"] += 1
            batch.append(chunk)
            bm25_ids.append(chunk.chunk_id)
            bm25_texts.append(f"{chunk.title} {chunk.section or ''} {chunk.text}")
            if len(batch) >= EMBED_BATCH:
                flush()
    flush()

    settings.index_dir.mkdir(parents=True, exist_ok=True)
    BM25Index().build(bm25_ids, bm25_texts).save(settings.index_dir / "bm25.pkl")
    if isinstance(store, InMemoryVectorStore):
        store.save(settings.index_dir / "dense")

    manifest = {
        "documents_seen": stats["documents_seen"],
        "documents_indexed": stats["documents_indexed"],
        "duplicates_dropped": dedup.dropped,
        "chunks": stats["chunks"],
        "superseded_chunks": stats["superseded_chunks"],
        "by_source": {k.split(":", 1)[1]: v for k, v in stats.items() if k.startswith("source:")},
        "licences": dict(licences),
        "embedding_model": settings.embedding_model if settings.embedding_backend != "hashing" else "hashing",
        "vector_backend": settings.vector_backend,
        "seconds": round(time.perf_counter() - started, 1),
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (settings.index_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log.info("index_built", **manifest)
    return manifest


def run(settings: Settings, config_path: Path, sources: list[str], limit_per_job: int | None,
        from_raw: bool = False) -> dict:
    config = load_corpus_config(config_path)
    raw_dir = settings.data_dir / "raw"
    if not from_raw:
        asyncio.run(harvest(sources, config, raw_dir, limit_per_job))
    return index_documents(settings, iter_raw(raw_dir, sources))
