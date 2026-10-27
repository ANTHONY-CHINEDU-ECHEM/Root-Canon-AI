"""Vector store abstraction with Qdrant (production) and in memory (tests) backends.

Chunk metadata is stored as payload so the API can filter by source type,
jurisdiction or evidence level directly inside the vector search.
"""

from __future__ import annotations

import abc
import json
import uuid
from pathlib import Path

import numpy as np

from backend.app.domain import Chunk


class VectorStore(abc.ABC):
    @abc.abstractmethod
    def upsert(self, chunks: list[Chunk], vectors: np.ndarray) -> None: ...

    @abc.abstractmethod
    def search(self, vector: np.ndarray, top_k: int, filters: dict | None = None) -> list[tuple[Chunk, float]]: ...

    @abc.abstractmethod
    def get(self, chunk_ids: list[str]) -> list[Chunk]: ...

    @abc.abstractmethod
    def count(self) -> int: ...


def _matches(chunk: Chunk, filters: dict | None) -> bool:
    if not filters:
        return True
    for key, allowed in filters.items():
        value = getattr(chunk, key, None)
        value = value.value if hasattr(value, "value") else value
        if key == "min_evidence_level":
            if int(chunk.evidence_level) < int(allowed):
                return False
        elif isinstance(allowed, list | tuple | set):
            if value not in allowed:
                return False
        elif value != allowed:
            return False
    return True


class InMemoryVectorStore(VectorStore):
    def __init__(self, dim: int) -> None:
        self.dim = dim
        self._chunks: list[Chunk] = []
        self._by_id: dict[str, int] = {}
        self._matrix = np.zeros((0, dim), dtype=np.float32)

    def upsert(self, chunks: list[Chunk], vectors: np.ndarray) -> None:
        new_rows = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            if chunk.chunk_id in self._by_id:
                row = self._by_id[chunk.chunk_id]
                self._chunks[row] = chunk
                self._matrix[row] = vector
            else:
                self._by_id[chunk.chunk_id] = len(self._chunks) + len(new_rows)
                new_rows.append((chunk, vector))
        if new_rows:
            self._chunks.extend(c for c, _ in new_rows)
            self._matrix = np.vstack([self._matrix, np.vstack([v for _, v in new_rows])]).astype(np.float32)

    def search(self, vector: np.ndarray, top_k: int, filters: dict | None = None) -> list[tuple[Chunk, float]]:
        if not self._chunks:
            return []
        scores = self._matrix @ vector.astype(np.float32)
        order = np.argsort(-scores)
        results = []
        for row in order:
            chunk = self._chunks[row]
            if _matches(chunk, filters):
                results.append((chunk, float(scores[row])))
                if len(results) >= top_k:
                    break
        return results

    def get(self, chunk_ids: list[str]) -> list[Chunk]:
        return [self._chunks[self._by_id[c]] for c in chunk_ids if c in self._by_id]

    def all_chunks(self) -> list[Chunk]:
        return list(self._chunks)

    def count(self) -> int:
        return len(self._chunks)

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        np.save(directory / "vectors.npy", self._matrix)
        with (directory / "chunks.jsonl").open("w", encoding="utf-8") as handle:
            for chunk in self._chunks:
                handle.write(chunk.model_dump_json() + "\n")

    @classmethod
    def load(cls, directory: Path) -> InMemoryVectorStore:
        matrix = np.load(directory / "vectors.npy")
        store = cls(matrix.shape[1])
        chunks = [Chunk.model_validate(json.loads(line)) for line in
                  (directory / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        store.upsert(chunks, matrix)
        return store


class QdrantVectorStore(VectorStore):
    def __init__(self, url: str, collection: str, dim: int) -> None:
        from qdrant_client import QdrantClient
        from qdrant_client.http import models as qm

        self._qm = qm
        self.client = QdrantClient(url=url, timeout=30)
        self.collection = collection
        if not self.client.collection_exists(collection):
            self.client.create_collection(
                collection_name=collection,
                vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE, on_disk=True),
                hnsw_config=qm.HnswConfigDiff(m=32, ef_construct=256),
                optimizers_config=qm.OptimizersConfigDiff(indexing_threshold=20_000),
            )
            for field in ("source", "source_type", "jurisdiction"):
                self.client.create_payload_index(collection, field, qm.PayloadSchemaType.KEYWORD)
            self.client.create_payload_index(collection, "evidence_level", qm.PayloadSchemaType.INTEGER)

    @staticmethod
    def _point_id(chunk_id: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))

    def upsert(self, chunks: list[Chunk], vectors: np.ndarray) -> None:
        points = [
            self._qm.PointStruct(id=self._point_id(c.chunk_id), vector=v.tolist(), payload=c.model_dump(mode="json"))
            for c, v in zip(chunks, vectors, strict=True)
        ]
        for start in range(0, len(points), 256):
            self.client.upsert(self.collection, points=points[start:start + 256], wait=False)

    def _filter(self, filters: dict | None):  # type: ignore[no-untyped-def]
        if not filters:
            return None
        qm, must = self._qm, []
        for key, allowed in filters.items():
            if key == "min_evidence_level":
                must.append(qm.FieldCondition(key="evidence_level", range=qm.Range(gte=int(allowed))))
            elif isinstance(allowed, list | tuple | set):
                must.append(qm.FieldCondition(key=key, match=qm.MatchAny(any=list(allowed))))
            else:
                must.append(qm.FieldCondition(key=key, match=qm.MatchValue(value=allowed)))
        return qm.Filter(must=must)

    def search(self, vector: np.ndarray, top_k: int, filters: dict | None = None) -> list[tuple[Chunk, float]]:
        hits = self.client.query_points(
            self.collection, query=vector.tolist(), limit=top_k, query_filter=self._filter(filters),
            search_params=self._qm.SearchParams(hnsw_ef=128), with_payload=True,
        ).points
        return [(Chunk.model_validate(h.payload), float(h.score)) for h in hits]

    def get(self, chunk_ids: list[str]) -> list[Chunk]:
        records = self.client.retrieve(self.collection, ids=[self._point_id(c) for c in chunk_ids], with_payload=True)
        return [Chunk.model_validate(r.payload) for r in records]

    def count(self) -> int:
        return int(self.client.count(self.collection, exact=False).count)
