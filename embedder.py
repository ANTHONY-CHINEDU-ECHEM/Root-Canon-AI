"""Embedding backends.

SentenceTransformerEmbedder is the production default (BGE base, 768 dims,
query instruction prefix as recommended by its authors). HashingEmbedder is a
deterministic, dependency free fallback used in tests and in offline CI where
model weights cannot be downloaded. It is a real feature hashing model over
word and character n grams, not a mock, so retrieval tests stay meaningful.
"""

from __future__ import annotations

import abc
import hashlib
import re
from functools import lru_cache

import numpy as np

_WORD = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?")


class Embedder(abc.ABC):
    dim: int

    @abc.abstractmethod
    def embed_documents(self, texts: list[str]) -> np.ndarray: ...

    @abc.abstractmethod
    def embed_query(self, text: str) -> np.ndarray: ...


class HashingEmbedder(Embedder):
    def __init__(self, dim: int = 768) -> None:
        self.dim = dim

    def _features(self, text: str) -> list[str]:
        words = _WORD.findall(text.lower())
        grams = words + [f"{a}_{b}" for a, b in zip(words, words[1:], strict=False)]
        for word in words:
            padded = f"#{word}#"
            grams.extend(padded[i:i + 4] for i in range(max(1, len(padded) - 3)))
        return grams

    def _embed(self, text: str) -> np.ndarray:
        vector = np.zeros(self.dim, dtype=np.float32)
        for feature in self._features(text):
            digest = hashlib.md5(feature.encode(), usedforsecurity=False).digest()
            index = int.from_bytes(digest[:4], "little") % self.dim
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign
        norm = np.linalg.norm(vector)
        return vector / norm if norm else vector

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return np.vstack([self._embed(t) for t in texts]) if texts else np.zeros((0, self.dim), np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        return self._embed(text)


class SentenceTransformerEmbedder(Embedder):
    QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

    def __init__(self, model_name: str, batch_size: int = 64) -> None:
        from sentence_transformers import SentenceTransformer  # heavy import kept lazy

        self.model = SentenceTransformer(model_name)
        self.dim = int(self.model.get_sentence_embedding_dimension())
        self.batch_size = batch_size
        self._prefix = self.QUERY_PREFIX if "bge" in model_name.lower() else ""

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return self.model.encode(texts, batch_size=self.batch_size, normalize_embeddings=True,
                                 show_progress_bar=len(texts) > 1000, convert_to_numpy=True)

    def embed_query(self, text: str) -> np.ndarray:
        return self.model.encode(self._prefix + text, normalize_embeddings=True, convert_to_numpy=True)


@lru_cache(maxsize=2)
def build_embedder(backend: str, model_name: str, dim: int = 768) -> Embedder:
    if backend == "hashing":
        return HashingEmbedder(dim)
    return SentenceTransformerEmbedder(model_name)
