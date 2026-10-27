"""Build the standalone interactive demo from the real seed corpus and formulary.

The demo page embeds the chunked UK guidance and the formulary so it runs
entirely in the browser (BM25 retrieval, guardrails, deterministic tools) and
can be hosted anywhere as a single file.

    python -m scripts.build_demo   ->   demo/index.html
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from backend.app.clinical.tools import formulary
from ingestion.processing.chunker import chunk_document
from ingestion.processing.evidence import EVIDENCE_LABELS, grade_evidence
from ingestion.seed import seed_documents

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    docs = seed_documents()
    chunks = [c for d in docs for c in chunk_document(d)]
    per_doc = Counter(c.doc_id for c in chunks)
    data = {
        "chunks": [{
            "doc_id": c.doc_id, "title": c.title, "section": (c.section or "").title(), "text": c.text, "url": c.url,
            "evidence_level": int(c.evidence_level), "evidence": EVIDENCE_LABELS[c.evidence_level],
            "year": c.published_year, "jurisdiction": c.jurisdiction,
        } for c in chunks],
        "docs": [{
            "title": d.title, "url": d.url, "publisher": d.publisher, "year": d.published.year if d.published else None,
            "licence": d.licence.value, "evidence_level": int(grade_evidence(d)),
            "evidence": EVIDENCE_LABELS[grade_evidence(d)], "passages": per_doc[d.doc_id],
        } for d in docs],
        "formulary": formulary(),
    }
    template = (ROOT / "demo" / "template.html").read_text(encoding="utf-8")
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    (ROOT / "demo" / "index.html").write_text(template.replace("/*__DATA__*/null", payload), encoding="utf-8")
    print(f"demo/index.html built: {len(docs)} documents, {len(chunks)} passages")


if __name__ == "__main__":
    main()
