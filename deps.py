"""Dependency container, authentication and rate limiting."""

from __future__ import annotations

import hashlib
import json
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request, status

from backend.app.config import Settings, get_settings
from backend.app.generation.rag_pipeline import RAGPipeline
from backend.app.llm.factory import build_provider
from backend.app.logging_setup import get_logger
from backend.app.retrieval.bm25 import BM25Index
from backend.app.retrieval.embedder import build_embedder
from backend.app.retrieval.hybrid import HybridRetriever
from backend.app.retrieval.reranker import build_reranker
from backend.app.retrieval.vector_store import InMemoryVectorStore, QdrantVectorStore, VectorStore

log = get_logger("api.deps")


@dataclass
class Container:
    settings: Settings
    retriever: HybridRetriever
    pipeline: RAGPipeline
    store: VectorStore
    cache: object | None = None

    def pipeline_for(self, provider: str | None) -> RAGPipeline:
        if not provider or provider == self.settings.llm_provider:
            return self.pipeline
        return RAGPipeline(self.settings, self.retriever, build_provider(self.settings, provider))


def build_container(settings: Settings | None = None) -> Container:
    settings = settings or get_settings()
    embedder = build_embedder(settings.embedding_backend, settings.embedding_model, settings.embedding_dim)
    if settings.vector_backend == "qdrant":
        store: VectorStore = QdrantVectorStore(settings.qdrant_url, settings.qdrant_collection, embedder.dim)
    else:
        dense_dir = settings.index_dir / "dense"
        store = InMemoryVectorStore.load(dense_dir) if dense_dir.exists() else InMemoryVectorStore(embedder.dim)
    bm25_path = settings.index_dir / "bm25.pkl"
    bm25 = BM25Index.load(bm25_path) if bm25_path.exists() else BM25Index()
    reranker = build_reranker(settings.reranker_backend, settings.reranker_model)
    retriever = HybridRetriever(settings, embedder, store, bm25, reranker)
    pipeline = RAGPipeline(settings, retriever, build_provider(settings))
    cache = None
    if settings.redis_url:
        try:
            import redis

            cache = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=1)
            cache.ping()
        except Exception as exc:  # noqa: BLE001 - cache is optional
            log.warning("cache_disabled", error=str(exc))
            cache = None
    log.info("container_ready", chunks=store.count(), bm25=len(bm25), provider=pipeline.provider.name)
    return Container(settings, retriever, pipeline, store, cache)


def get_container(request: Request) -> Container:
    return request.app.state.container


def cache_key(*parts: object) -> str:
    return "rc:answer:" + hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


def get_app_settings(request: Request) -> Settings:
    return request.app.state.container.settings


async def require_api_key(x_api_key: str | None = Header(default=None),
                          settings: Settings = Depends(get_app_settings)) -> str:
    # Local development without a key is allowed so the demo UI works out of the box.
    if settings.env == "development" and not x_api_key:
        return "development"
    if not x_api_key or x_api_key not in settings.api_keys:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing or invalid X-API-Key")
    return x_api_key


_WINDOWS: dict[str, deque[float]] = defaultdict(deque)


async def rate_limit(request: Request, api_key: str = Depends(require_api_key),
                     settings: Settings = Depends(get_app_settings)) -> None:
    identity = f"{api_key}:{request.client.host if request.client else 'unknown'}"
    window, now = _WINDOWS[identity], time.monotonic()
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= settings.rate_limit_per_minute:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Rate limit exceeded, try again shortly")
    window.append(now)
