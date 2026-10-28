"""Clinical query understanding.

Turns free text such as "Pt on Eliquis, 6 yr old needs amoxil, how much?" into
structured facts the rest of the system can act on deterministically:

  * a normalised query with UK spelling and generic drug names, used for
    retrieval so "Xarelto" finds guidance that only says "rivaroxaban";
  * the medicines mentioned, with their drug classes;
  * the patient's age and weight when stated;
  * the intents present (dose, maximum dose, interaction, referral, ...).

Everything here is rule based and reviewed in `knowledge/lexicon.yaml`; no
model is involved, so extraction is reproducible and testable.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache

from backend.app.knowledge import load

_AGE_PATTERNS: tuple[tuple[re.Pattern[str], float], ...] = (
    # "18 month old", "6-month-old"
    (re.compile(r"\b(\d{1,2})[\s-]*(?:months?|mths?)[\s-]*old\b", re.I), 1 / 12),
    # "3 year old", "3-year-old", "45 yrs old"
    (re.compile(r"\b(\d{1,3}(?:\.\d)?)[\s-]*(?:years?|yrs?|yr)[\s-]*old\b", re.I), 1.0),
    # "45yo", "45 y/o"
    (re.compile(r"\b(\d{1,3})\s*(?:yo|y/o|y\.o\.)(?![a-z])", re.I), 1.0),
    # "aged 9 months", "age: 9 months"
    (re.compile(r"\b(?:aged?)[:\s]+(\d{1,2})\s*(?:months?|mths?)\b", re.I), 1 / 12),
    # "aged 7", "age 7", "age: 70 years"
    (re.compile(r"\b(?:aged?)[:\s]+(\d{1,3}(?:\.\d)?)\b(?!\s*(?:months?|mths?|kg|mg))", re.I), 1.0),
)
_WEIGHT = re.compile(r"\b(\d{1,3}(?:\.\d)?)\s*(?:kg|kilograms?|kilos?)\b", re.I)
_CHILD_WORDS = re.compile(r"\b(child|children|paediatric|pediatric|infant|toddler|baby|kid)\b", re.I)


@dataclass(frozen=True)
class ClinicalEntities:
    original: str
    normalised: str
    drugs: tuple[str, ...] = ()
    classes: frozenset[str] = field(default_factory=frozenset)
    age_years: float | None = None
    weight_kg: float | None = None
    intents: frozenset[str] = field(default_factory=frozenset)
    mentions_child: bool = False

    @property
    def expansion(self) -> str:
        """Generic names to append to the retrieval query (only ones not already present)."""
        lowered = self.original.lower()
        return " ".join(d for d in self.drugs if d not in lowered)

    def as_dict(self) -> dict:
        return {
            "drugs": list(self.drugs),
            "classes": sorted(self.classes),
            "age_years": self.age_years,
            "weight_kg": self.weight_kg,
            "intents": sorted(self.intents),
            "normalised": self.normalised,
        }


@lru_cache(maxsize=1)
def _lexicon() -> tuple[list[tuple[re.Pattern[str], str]], list[tuple[re.Pattern[str], str]],
                        dict[str, set[str]], list[tuple[re.Pattern[str], str]], dict[str, list[str]]]:
    data = load("lexicon")
    # Longest names first so "penicillin v" wins over any shorter overlap.
    synonyms = sorted(data["synonyms"].items(), key=lambda kv: -len(kv[0]))
    synonym_patterns = [(re.compile(rf"\b{re.escape(k)}\b", re.I), v) for k, v in synonyms]
    spelling_patterns = [(re.compile(rf"\b{re.escape(us)}", re.I), uk) for us, uk in data["spellings"].items()]
    class_of: dict[str, set[str]] = {}
    for cls, members in data["drug_classes"].items():
        for member in members:
            class_of.setdefault(member, set()).add(cls)
    generic_patterns = [(re.compile(rf"\b{re.escape(name)}\b", re.I), name)
                        for name in sorted(class_of, key=lambda n: -len(n))]
    return synonym_patterns, spelling_patterns, class_of, generic_patterns, data["intents"]


def normalise(text: str) -> str:
    """UK spelling and generic names, preserving the rest of the text exactly."""
    synonym_patterns, spelling_patterns, *_ = _lexicon()
    for pattern, target in spelling_patterns:
        text = pattern.sub(_case_preserving(target), text)
    for pattern, generic in synonym_patterns:
        text = pattern.sub(generic, text)
    return text


def _case_preserving(replacement: str) -> Callable[[re.Match[str]], str]:
    def replace(match: re.Match[str]) -> str:
        return replacement.capitalize() if match.group(0)[:1].isupper() else replacement

    return replace


def _age(text: str) -> float | None:
    for pattern, scale in _AGE_PATTERNS:
        match = pattern.search(text)
        if match:
            value = float(match.group(1)) * scale
            if 0 <= value <= 120:
                return round(value, 2)
    return None


def _weight(text: str) -> float | None:
    match = _WEIGHT.search(text)
    if match:
        value = float(match.group(1))
        if 1 <= value <= 300:
            return value
    return None


def extract(text: str) -> ClinicalEntities:
    _, _, class_of, generic_patterns, intents = _lexicon()
    normalised = normalise(text)
    lowered = normalised.lower()

    drugs: list[str] = []
    for pattern, name in generic_patterns:
        if pattern.search(normalised) and not any(name in found for found in drugs):
            drugs.append(name)
    # Keep the order in which the clinician mentioned them.
    drugs.sort(key=lambda d: lowered.find(d))
    classes = frozenset(cls for d in drugs for cls in class_of.get(d, ()))
    found_intents = frozenset(name for name, cues in intents.items() if any(cue in lowered for cue in cues))

    return ClinicalEntities(
        original=text,
        normalised=normalised,
        drugs=tuple(drugs),
        classes=classes,
        age_years=_age(normalised),
        weight_kg=_weight(normalised),
        intents=found_intents,
        mentions_child=bool(_CHILD_WORDS.search(normalised)),
    )


def drug_class_members(cls: str) -> list[str]:
    return list(load("lexicon")["drug_classes"].get(cls, []))
