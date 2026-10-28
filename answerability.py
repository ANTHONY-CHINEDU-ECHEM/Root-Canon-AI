"""Answerability: does the retrieved evidence actually talk about the question?

The evidence gate in the original pipeline looked only at the best passage's
score. A question about a topic the knowledge base does not cover (zirconia
implant survival, a manufacturer's torque setting) still retrieves the nearest
passages, and those can score respectably on shared words such as "implant".

Query coverage measures the share of the question's informative terms, weighted
by inverse document frequency, that occur anywhere in the top passages. Rare,
specific words (the ones that make the question that question) dominate the
weight, so missing them pulls coverage down sharply. Below the configured
threshold the pipeline abstains before spending a model call. Emergencies are
never gated on coverage: the triage banner and emergency guidance always go out.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.app.domain import RetrievedChunk
from backend.app.retrieval.bm25 import BM25Index, tokenize

# Question words and generic clinical verbs that say nothing about the topic.
_UNINFORMATIVE = frozenset([
    "also", "any", "been", "but", "each", "either", "into", "may", "more", "most", "must", "need", "needs", "not",
    "only", "other", "such", "than", "then", "there", "these", "they", "those", "under", "used", "using", "very",
    "where", "whether", "while", "who", "would", "your", "their", "them", "about", "after", "before", "between",
    "both", "what", "which", "when", "how", "should", "does", "dose", "doses", "patient", "patients", "give",
    "given", "take", "taking", "advice", "recommend", "recommended",
])


@dataclass
class Answerability:
    coverage: float
    missing_terms: list[str] = field(default_factory=list)


def query_coverage(question: str, chunks: list[RetrievedChunk], bm25: BM25Index, top_n: int = 5) -> Answerability:
    terms = [t for t in dict.fromkeys(tokenize(question)) if t not in _UNINFORMATIVE and len(t) > 2]
    if not terms or not chunks:
        return Answerability(1.0 if not terms else 0.0, terms)
    pool: set[str] = set()
    for item in chunks[:top_n]:
        c = item.chunk
        pool.update(tokenize(f"{c.title} {c.section or ''} {c.text}"))
    weights = {t: bm25.idf(t) for t in terms}
    total = sum(weights.values()) or 1.0
    covered = sum(w for t, w in weights.items() if t in pool)
    return Answerability(round(covered / total, 3), [t for t in terms if t not in pool])
