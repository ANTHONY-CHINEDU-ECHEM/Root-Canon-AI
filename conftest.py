from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.config import Settings
from backend.app.generation.rag_pipeline import RAGPipeline
from backend.app.llm.factory import ExtractiveProvider
from backend.app.retrieval.bm25 import BM25Index
from backend.app.retrieval.embedder import HashingEmbedder
from backend.app.retrieval.hybrid import HybridRetriever
from backend.app.retrieval.reranker import LexicalOverlapReranker
from backend.app.retrieval.vector_store import InMemoryVectorStore
from ingestion.processing.chunker import chunk_document, contextualise
from ingestion.seed import seed_documents


@pytest.fixture(scope="session")
def settings(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    data_dir: Path = tmp_path_factory.mktemp("data")
    return Settings(env="test", data_dir=data_dir, embedding_backend="hashing", reranker_backend="none",
                    vector_backend="memory", redis_url=None, llm_provider="fake", min_evidence_score=0.1)


@pytest.fixture(scope="session")
def seed_chunks():
    return [chunk for doc in seed_documents() for chunk in chunk_document(doc)]


@pytest.fixture(scope="session")
def retriever(settings: Settings, seed_chunks) -> HybridRetriever:
    embedder = HashingEmbedder(settings.embedding_dim)
    store = InMemoryVectorStore(embedder.dim)
    store.upsert(seed_chunks, embedder.embed_documents([contextualise(c) for c in seed_chunks]))
    bm25 = BM25Index().build([c.chunk_id for c in seed_chunks],
                             [f"{c.title} {c.section} {c.text}" for c in seed_chunks])
    return HybridRetriever(settings, embedder, store, bm25, LexicalOverlapReranker())


@pytest.fixture(scope="session")
def pipeline(settings: Settings, retriever: HybridRetriever) -> RAGPipeline:
    return RAGPipeline(settings, retriever, ExtractiveProvider())
