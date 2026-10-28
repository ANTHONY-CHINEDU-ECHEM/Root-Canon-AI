"""Medication safety screen.

Compares what the dentist plans to prescribe with what the patient already
takes and the conditions recorded in the de identified patient context, and
returns prioritised flags. It combines three deterministic layers:

  1. the curated pairwise interaction table in the formulary,
  2. class rules about the patient's own medicines (anticoagulants,
     antiplatelets, antiresorptives) from `knowledge/safety_rules.yaml`,
  3. condition and allergy rules for the planned prescription.

The screen never produces a dose. An empty result means only that no rule
fired, which the response states explicitly.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from functools import lru_cache

from backend.app.clinical import entities, tools
from backend.app.knowledge import load

SEVERITY_ORDER = {"contraindicated": 0, "major": 1, "moderate": 2, "caution": 3, "minor": 4}
NO_FINDINGS_NOTE = (
    "No rule in the curated dental set fired. This is not proof of safety: check the BNF interactions appendix "
    "and the patient's full medical history."
)


@dataclass
class SafetyFlag:
    kind: str                 # interaction | patient_medicine | condition
    severity: str
    title: str
    message: str
    drugs: list[str] = field(default_factory=list)
    source_url: str = ""
    rule_id: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class SafetyScreen:
    planned: list[str]
    current: list[str]
    flags: list[SafetyFlag]
    note: str

    @property
    def highest_severity(self) -> str | None:
        return self.flags[0].severity if self.flags else None

    def as_dict(self) -> dict:
        return {"planned": self.planned, "current": self.current, "highest_severity": self.highest_severity,
                "flags": [f.as_dict() for f in self.flags], "note": self.note}


@lru_cache(maxsize=1)
def _rules() -> dict:
    data = load("safety_rules")
    for rule in data.get("conditions", []):
        rule["_compiled"] = [re.compile(p, re.IGNORECASE) for p in rule["patterns"]]
    return data


def _source(key: str) -> str:
    return _rules()["sources"].get(key, "")


def _classes(drugs: list[str]) -> set[str]:
    return set(entities.extract(" ".join(drugs)).classes) if drugs else set()


def screen(planned: list[str], current: list[str] | None = None, patient_context: str | None = None) -> SafetyScreen:
    """Run the screen.

    `planned` and `current` may be names or brand names; `patient_context` is
    free text (already de identified by the caller) that is mined for further
    medicines and for conditions and allergies.
    """
    planned_names = list(dict.fromkeys(
        d for item in planned for d in (entities.extract(item).drugs or (item.strip().lower(),)) if d))
    context_entities = entities.extract(patient_context) if patient_context else None
    current_names = list(dict.fromkeys(
        [d for item in (current or []) for d in (entities.extract(item).drugs or (item.strip().lower(),)) if d]
        + (list(context_entities.drugs) if context_entities else [])))
    current_names = [d for d in current_names if d not in planned_names]

    flags: list[SafetyFlag] = []

    # 1. Pairwise interactions between planned and current medicines (and within the plan).
    pool = planned_names + current_names
    for hit in tools.check_interactions(pool):
        if hit["a"] in planned_names or hit["b"] in planned_names:
            flags.append(SafetyFlag("interaction", hit["severity"], f"{hit['a'].capitalize()} with {hit['b']}",
                                    hit["effect"], [hit["a"], hit["b"]], "https://bnf.nice.org.uk/interactions/",
                                    f"ix:{hit['a']}:{hit['b']}"))

    rules = _rules()
    # 2. The patient's own medicines.
    current_classes = _classes(current_names)
    for rule in rules.get("patient_medicines", []):
        matched = [d for d in current_names if _classes([d]) & set(rule["classes"])]
        if current_classes & set(rule["classes"]) and matched:
            flags.append(SafetyFlag("patient_medicine", rule["severity"], rule["title"], rule["message"].strip(),
                                    matched, _source(rule["source"]), rule["id"]))

    # 3. Conditions and allergies against the planned prescription.
    planned_classes = _classes(planned_names)
    text = patient_context or ""
    for rule in rules.get("conditions", []):
        relevant = planned_classes & set(rule.get("planned_classes", []))
        if rule.get("planned_drugs"):
            relevant = relevant if set(rule["planned_drugs"]) & set(planned_names) else set()
        if relevant and any(p.search(text) for p in rule["_compiled"]):
            drugs = [d for d in planned_names if _classes([d]) & relevant]
            flags.append(SafetyFlag("condition", rule["severity"], rule["title"], rule["message"].strip(),
                                    drugs, _source(rule["source"]), rule["id"]))

    # Deduplicate (the metronidazole and alcohol pair can arrive from two layers).
    unique: dict[tuple[str, frozenset[str]], SafetyFlag] = {}
    for flag in flags:
        key = (flag.title.lower() if flag.kind != "interaction" else "ix", frozenset(flag.drugs))
        existing = unique.get(key)
        if existing is None or SEVERITY_ORDER.get(flag.severity, 9) < SEVERITY_ORDER.get(existing.severity, 9):
            unique[key] = flag
    ordered = sorted(unique.values(), key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), f.title))
    note = ("Flags are decision support from a curated dental rule set. Confirm against the BNF and the "
            "patient's full history." if ordered else NO_FINDINGS_NOTE)
    return SafetyScreen(planned_names, current_names, ordered, note)
