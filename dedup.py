"""Near duplicate detection with SimHash.

The same abstract often arrives from PubMed and Europe PMC, and drug labels
are republished by many manufacturers with trivial differences. Indexing
duplicates wastes context window and over weights one source, so documents
whose 64 bit SimHash fingerprints differ by at most `max_distance` bits are
collapsed, keeping the copy with the richer licence and more sections.
"""

from __future__ import annotations

import hashlib
import re

from backend.app.domain import Licence, SourceDocument

_TOKEN = re.compile(r"[a-z0-9]+")
_LICENCE_RANK = {
    Licence.OPEN_GOVERNMENT: 5, Licence.CC0: 5, Licence.CC_BY: 4, Licence.PUBLIC_DOMAIN_US_GOV: 4,
    Licence.SYNDICATION_LICENSED: 3, Licence.CC_BY_NC: 2, Licence.ABSTRACT_FAIR_DEALING: 1, Licence.UNKNOWN: 0,
}


def _shingles(text: str, size: int = 3) -> list[str]:
    tokens = _TOKEN.findall(text.lower())
    return [" ".join(tokens[i:i + size]) for i in range(max(1, len(tokens) - size + 1))]


def simhash(text: str, bits: int = 64) -> int:
    weights = [0] * bits
    for shingle in _shingles(text):
        digest = int.from_bytes(hashlib.blake2b(shingle.encode(), digest_size=8).digest(), "big")
        for bit in range(bits):
            weights[bit] += 1 if digest >> bit & 1 else -1
    return sum(1 << bit for bit in range(bits) if weights[bit] > 0)


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


class Deduplicator:
    """Streaming deduplicator using banded buckets for sub linear lookups."""

    def __init__(self, max_distance: int = 3, bands: int = 4) -> None:
        self.max_distance = max_distance
        self.bands = bands
        self._band_bits = 64 // bands
        self._buckets: dict[tuple[int, int], list[tuple[int, SourceDocument]]] = {}
        self.dropped = 0

    def _keys(self, fingerprint: int) -> list[tuple[int, int]]:
        mask = (1 << self._band_bits) - 1
        return [(band, (fingerprint >> (band * self._band_bits)) & mask) for band in range(self.bands)]

    @staticmethod
    def licence_rank(document: SourceDocument) -> int:
        return _LICENCE_RANK[document.licence]

    def add(self, document: SourceDocument) -> SourceDocument | None:
        """Return the document if it is new, or None if it duplicates one already seen."""
        fingerprint = simhash(document.title + " " + document.text[:4000])
        for key in self._keys(fingerprint):
            for existing_fp, _existing in self._buckets.get(key, []):
                if hamming(fingerprint, existing_fp) <= self.max_distance:
                    # First seen wins. The pipeline ingests sources in licence
                    # priority order (guidance, open full text, then abstracts)
                    # so the first copy is already the preferred one.
                    self.dropped += 1
                    return None
        for key in self._keys(fingerprint):
            self._buckets.setdefault(key, []).append((fingerprint, document))
        return document
