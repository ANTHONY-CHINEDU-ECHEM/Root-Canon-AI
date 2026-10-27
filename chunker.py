"""Structure aware chunking.

Chunks never cross a section boundary, so a RESULTS paragraph is never glued to
a METHODS paragraph and a dosing box is never split from its heading. Within a
section, text is packed sentence by sentence up to a token budget with a small
sentence overlap so that a claim and its qualifier stay together.

Each chunk is prefixed with a compact context header (document title and
section) which measurably improves dense retrieval for short clinical queries.
"""

from __future__ import annotations

import hashlib
import re

from backend.app.domain import Chunk, SourceDocument
from ingestion.processing.cleaner import clean_text
from ingestion.processing.evidence import grade_evidence

# Sentence splitter that does not break on common clinical abbreviations or decimals.
_ABBREVIATIONS = r"(?<!\be\.g)(?<!\bi\.e)(?<!\bet al)(?<!\bvs)(?<!\bapprox)(?<!\bFig)(?<!\bNo)(?<!\bDr)"
_SENTENCE_END = re.compile(_ABBREVIATIONS + r"(?<=[.!?])\s+(?=[A-Z0-9\"(\[])")


def approx_tokens(text: str) -> int:
    """Fast token estimate (about 0.75 words per token for English biomedical prose)."""
    return max(1, int(len(text.split()) / 0.75))


def split_sentences(text: str) -> list[str]:
    sentences: list[str] = []
    for paragraph in text.split("\n"):
        paragraph = paragraph.strip()
        if paragraph:
            sentences.extend(s.strip() for s in _SENTENCE_END.split(paragraph) if s.strip())
    return sentences


def _chunk_id(doc_id: str, section: str, position: int, text: str) -> str:
    digest = hashlib.sha256(f"{doc_id}|{section}|{position}|{text}".encode()).hexdigest()[:16]
    return f"{doc_id}#{digest}"


def chunk_document(
    document: SourceDocument, max_tokens: int = 320, overlap_sentences: int = 1, min_tokens: int = 25
) -> list[Chunk]:
    evidence = grade_evidence(document)
    sections = document.sections or [("BODY", document.text)]
    year = (document.published or document.updated).year if (document.published or document.updated) else None
    chunks: list[Chunk] = []
    position = 0

    for heading, body in sections:
        sentences = split_sentences(clean_text(body))
        if not sentences:
            continue
        window: list[str] = []
        window_tokens = 0
        for sentence in sentences:
            sentence_tokens = approx_tokens(sentence)
            if window and window_tokens + sentence_tokens > max_tokens:
                chunks.append(_make_chunk(document, heading, position, window, evidence, year))
                position += 1
                window = window[-overlap_sentences:] if overlap_sentences else []
                window_tokens = sum(approx_tokens(s) for s in window)
            window.append(sentence)
            window_tokens += sentence_tokens
        if window and (window_tokens >= min_tokens or not chunks):
            chunks.append(_make_chunk(document, heading, position, window, evidence, year))
            position += 1
        elif window and chunks and chunks[-1].section == heading:
            # Merge a tiny tail into the previous chunk of the same section.
            tail = " ".join(window[overlap_sentences:])
            if tail:
                chunks[-1].text = f"{chunks[-1].text} {tail}"
                chunks[-1].token_count = approx_tokens(chunks[-1].text)
    return chunks


def _make_chunk(document, heading, position, sentences, evidence, year) -> Chunk:  # type: ignore[no-untyped-def]
    body = " ".join(sentences)
    return Chunk(
        chunk_id=_chunk_id(document.doc_id, heading, position, body),
        doc_id=document.doc_id,
        text=body,
        section=heading,
        title=clean_text(document.title),
        url=document.url,
        source=document.source,
        source_type=document.source_type,
        evidence_level=evidence,
        published_year=year,
        jurisdiction=document.jurisdiction,
        licence=document.licence,
        token_count=approx_tokens(body),
        position=position,
    )


def contextualise(chunk: Chunk) -> str:
    """Text that is actually embedded: header plus body."""
    section = f" | {chunk.section.title()}" if chunk.section else ""
    return f"{chunk.title}{section}\n{chunk.text}"
