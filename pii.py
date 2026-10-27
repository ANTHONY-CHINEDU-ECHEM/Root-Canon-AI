"""Patient identifiable information redaction (UK GDPR, Caldicott principles).

Clinicians will paste fragments of records. Before any text leaves the
service (to an LLM vendor, to logs, to the cache) these identifiers are
replaced with typed placeholders. NHS numbers are validated with the modulus
11 check digit so ordinary 10 digit numbers are not over redacted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_NHS = re.compile(r"\b(\d{3})[ ]?(\d{3})[ ]?(\d{4})\b")
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("PHONE", re.compile(r"(?<!\d)(?:\+44\s?7\d{3}|07\d{3})\s?\d{3}\s?\d{3}(?!\d)|(?<!\d)0[12]\d{2,3}\s?\d{3}\s?\d{3,4}(?!\d)")),
    ("POSTCODE", re.compile(r"\b(?:[A-Z]{1,2}\d[A-Z\d]?)\s?\d[A-Z]{2}\b", re.IGNORECASE)),
    ("DATE_OF_BIRTH", re.compile(r"\b(?:dob|d\.o\.b\.?|date of birth|born)[:\s]*\d{1,2}[/.]\d{1,2}[/.]\d{2,4}\b", re.IGNORECASE)),
    ("NAME", re.compile(r"\b(?:Mr|Mrs|Ms|Miss|Mx|Dr|Master)\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b")),
]


def valid_nhs_number(digits: str) -> bool:
    if len(digits) != 10 or not digits.isdigit():
        return False
    total = sum(int(d) * w for d, w in zip(digits[:9], range(10, 1, -1), strict=True))
    check = 11 - (total % 11)
    check = 0 if check == 11 else check
    return check != 10 and check == int(digits[9])


@dataclass
class RedactionResult:
    text: str
    found: dict[str, int] = field(default_factory=dict)

    @property
    def redacted(self) -> bool:
        return bool(self.found)


def redact(text: str) -> RedactionResult:
    found: dict[str, int] = {}

    def nhs_sub(match: re.Match[str]) -> str:
        digits = "".join(match.groups())
        if valid_nhs_number(digits):
            found["NHS_NUMBER"] = found.get("NHS_NUMBER", 0) + 1
            return "[NHS_NUMBER]"
        return match.group(0)

    text = _NHS.sub(nhs_sub, text)
    for label, pattern in _PATTERNS:
        text, count = pattern.subn(f"[{label}]", text)
        if count:
            found[label] = found.get(label, 0) + count
    return RedactionResult(text, found)
