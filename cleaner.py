"""Text normalisation that preserves clinical meaning.

Dental text is full of tokens that naive cleaners destroy: drug strengths
(500 mg), concentrations (1:80,000), tooth notation (UR6, 36), fluoride levels
(1,450 ppm) and Greek letters. This cleaner only fixes encoding artefacts and
whitespace; it never lowercases or strips punctuation.
"""

from __future__ import annotations

import re
import unicodedata

_WS = re.compile(r"[ \t   ]+")
_MULTI_NL = re.compile(r"\n{3,}")
_REPLACEMENTS = {
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": " - ",
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "µg": "microgram", "μg": "microgram", "mcg": "microgram",
    "ﬁ": "fi", "ﬂ": "fl",
}
_BOILERPLATE = [
    re.compile(r"Copyright ©.*?(?:\.|$)", re.IGNORECASE),
    re.compile(r"©\s*\d{4}.*?(?:\.|$)"),
    re.compile(r"This article is protected by copyright\. All rights reserved\.?", re.IGNORECASE),
    re.compile(r"Skip to (?:main )?content", re.IGNORECASE),
]


def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    for source, target in _REPLACEMENTS.items():
        text = text.replace(source, target)
    for pattern in _BOILERPLATE:
        text = pattern.sub("", text)
    text = _WS.sub(" ", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    return _MULTI_NL.sub("\n\n", text).strip()
