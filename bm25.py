"""Okapi BM25 sparse index with a clinical tokenizer.

Lexical retrieval matters in dentistry because many decisive terms are exact
tokens that dense models blur: drug names, "1:80,000", "5,000 ppm", "MRONJ",
"CG64". The tokenizer keeps numbers with units and ratios intact and expands
a curated set of UK dental abbreviations.
"""

from __future__ import annotations

import math
import pickle
import re
from collections import Counter
from pathlib import Path

import numpy as np

_TOKEN = re.compile(r"\d+(?:[.,:]\d+)*\s?(?:mg|g|ml|ppm|microgram|%)?|[a-z][a-z0-9]*")
_STOP = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "have",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "were",
        "will",
        "with",
        "which",
        "what",
        "when",
        "how",
        "should",
        "can",
        "does",
        "do",
        "i",
        "my",
        "me",
        "patient",
        "patients",
    ]
)
ABBREVIATIONS = {
    "mronj": "medication related osteonecrosis jaw",
    "ie": "infective endocarditis",
    "la": "local anaesthetic",
    "nsaid": "non steroidal anti inflammatory",
    "nsaids": "non steroidal anti inflammatory",
    "doac": "direct oral anticoagulant",
    "doacs": "direct oral anticoagulant",
    "inr": "international normalised ratio",
    "gtn": "glyceryl trinitrate",
    "anug": "necrotising ulcerative gingivitis",
    "bpe": "basic periodontal examination",
    "rct": "root canal treatment",
    "dbohs": "delivering better oral health",
    "dboh": "delivering better oral health",
    "warfarin": "anticoagulant",
    "apixaban": "anticoagulant",
    "rivaroxaban": "anticoagulant",
    "dabigatran": "anticoagulant",
    "edoxaban": "anticoagulant",
    "ibuprofen": "non steroidal anti inflammatory",
    "sdcep": "scottish dental clinical effectiveness programme",
}


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for raw in _TOKEN.findall(text.lower()):
        token = raw.replace(" ", "").replace(",", "")
        if token in _STOP or len(token) < 2 and not token.isdigit():
            continue
        tokens.append(token)
        if token in ABBREVIATIONS:
            tokens.extend(ABBREVIATIONS[token].split())
        elif token.endswith("s") and len(token) > 4:
            tokens.append(token[:-1])  # light plural folding
    return tokens


class BM25Index:
    def __init__(self, k1: float = 1.4, b: float = 0.72) -> None:
        self.k1, self.b = k1, b
        self.ids: list[str] = []
        self._postings: dict[str, list[tuple[int, int]]] = {}
        self._doc_len: list[int] = []
        self._idf: dict[str, float] = {}
        self._avg_len = 0.0

    def __len__(self) -> int:
        return len(self.ids)

    def build(self, ids: list[str], texts: list[str]) -> BM25Index:
        self.ids = list(ids)
        self._postings.clear()
        self._doc_len = []
        for doc_index, text in enumerate(texts):
            counts = Counter(tokenize(text))
            self._doc_len.append(sum(counts.values()))
            for term, freq in counts.items():
                self._postings.setdefault(term, []).append((doc_index, freq))
        n = len(self.ids)
        self._avg_len = (sum(self._doc_len) / n) if n else 0.0
        self._idf = {t: math.log(1 + (n - len(p) + 0.5) / (len(p) + 0.5)) for t, p in self._postings.items()}
        return self

    def search(self, query: str, top_k: int = 40) -> list[tuple[str, float]]:
        if not self.ids:
            return []
        scores = np.zeros(len(self.ids), dtype=np.float32)
        for term in set(tokenize(query)):
            postings = self._postings.get(term)
            if not postings:
                continue
            idf = self._idf[term]
            for doc_index, freq in postings:
                norm = self.k1 * (1 - self.b + self.b * self._doc_len[doc_index] / (self._avg_len or 1))
                scores[doc_index] += idf * freq * (self.k1 + 1) / (freq + norm)
        top_k = min(top_k, len(self.ids))
        candidates = np.argpartition(-scores, top_k - 1)[:top_k]
        ranked = sorted(candidates, key=lambda i: -scores[i])
        return [(self.ids[i], float(scores[i])) for i in ranked if scores[i] > 0]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as handle:
            pickle.dump(self.__dict__, handle, protocol=pickle.HIGHEST_PROTOCOL)

    @classmethod
    def load(cls, path: Path) -> BM25Index:
        index = cls()
        with path.open("rb") as handle:
            index.__dict__.update(pickle.load(handle))  # noqa: S301 - file is produced by our own pipeline
        return index
