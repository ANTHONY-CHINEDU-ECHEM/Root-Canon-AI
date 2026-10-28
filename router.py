"""Deterministic tool routing.

The architecture keeps every safety critical number out of the language model.
This router reads the structured entities in a question (and the optional patient
context) and calls the deterministic clinical tools directly, so a question such
as "amoxicillin dose for a 3 year old" receives a verified regimen card from the
formulary alongside the cited narrative answer.

Cards are returned to the clinician as their own streamed event before the
model starts writing. They are never placed in the model's prompt, which keeps
the citation validator's number check honest: a figure in the narrative must
still come from a cited source.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from backend.app.clinical import safety_screen, tools
from backend.app.clinical.entities import ClinicalEntities, extract


@dataclass
class ToolCard:
    tool: str                  # regimen | local_anaesthetic | adrenaline | safety_screen
    title: str
    summary: str
    data: dict = field(default_factory=dict)
    source_url: str = ""
    verify: str = "Reference only. Confirm against the current BNF or BNFC and the patient's history."
    severity: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


_LA_NAMES = frozenset({"lidocaine", "articaine", "mepivacaine", "prilocaine"})


def _regimen_cards(q: ClinicalEntities) -> list[ToolCard]:
    if "dose" not in q.intents:
        return []
    available = set(tools.formulary()["regimens"])
    cards: list[ToolCard] = []
    for drug in q.drugs:
        if drug not in available:
            continue
        age = q.age_years
        if age is None and q.mentions_child:
            cards.append(ToolCard(
                "regimen", f"{drug.capitalize()}: child's age needed",
                "The question is about a child but gives no age. Paediatric doses are set by age band, so no "
                "adult dose is shown. Ask again with the child's age.", {"drug": drug}, severity="caution"))
            continue
        try:
            result = tools.lookup_regimen(drug, age)
        except ValueError as exc:
            cards.append(ToolCard("regimen", f"{drug.capitalize()}: no band on file", str(exc),
                                  {"drug": drug, "age_years": age}, severity="caution"))
            continue
        summary = f"{result.dose} {result.frequency}" + (f" for {result.duration}" if result.duration else "")
        cards.append(ToolCard("regimen", f"{drug.capitalize()} ({result.population})", summary, asdict(result),
                              result.source_url, result.verify_message))
    return cards


def _local_anaesthetic_cards(q: ClinicalEntities) -> list[ToolCard]:
    products = [d for d in q.drugs if d in _LA_NAMES]
    if not products or q.weight_kg is None:
        return []
    cards = []
    for product in products:
        try:
            limit = tools.local_anaesthetic_max(product, q.weight_kg)
        except (KeyError, ValueError):
            continue
        cards.append(ToolCard(
            "local_anaesthetic", f"Maximum {limit.product} for {q.weight_kg:g} kg",
            f"{limit.max_mg} mg, {limit.max_ml} mL, about {limit.max_cartridges} cartridges",
            asdict(limit), verify="Reference maximum. Use the lowest effective dose and confirm against the SmPC.",
        ))
    return cards


def _band_label(band: dict) -> str:
    low, high = band["min_age_years"], band["max_age_years"]
    if low >= 12:
        return f"{low:g} years and over"
    return f"{low:g} to under {high:g} years"


def _adrenaline_cards(q: ClinicalEntities, is_anaphylaxis: bool) -> list[ToolCard]:
    if not (is_anaphylaxis or ("emergency_drug" in q.intents and "adrenaline" in q.drugs)):
        return []
    if q.age_years is None:
        bands = tools.formulary()["emergency"]["adrenaline_anaphylaxis"]["age_bands"]
        summary = "; ".join(f"{_band_label(b)}: {b['dose']}" for b in bands)
        return [ToolCard("adrenaline", "Adrenaline 1:1000 intramuscular, dose by age", summary, {"age_bands": bands},
                         tools.formulary()["sources"]["rcuk_anaphylaxis"], severity="emergency")]
    result = tools.adrenaline_dose(q.age_years)
    return [ToolCard("adrenaline", f"Adrenaline for anaphylaxis, age {q.age_years:g}",
                     f"{result['dose']} intramuscularly. {result['repeat']}", result, result["source_url"],
                     severity="emergency")]


# Classes a dentist does not prescribe: when named in a question they describe what the patient already takes.
PATIENT_CLASSES = frozenset({"vitamin_k_antagonists", "doacs", "antiplatelets", "antiresorptives", "other_interacting"})


def _screen_cards(q: ClinicalEntities, patient_context: str | None) -> list[ToolCard]:
    context_drugs = list(extract(patient_context).drugs) if patient_context else []
    from_question = [d for d in q.drugs if set(extract(d).classes) & PATIENT_CLASSES and d != "aspirin"]
    current = list(dict.fromkeys(context_drugs + from_question))
    planned = [d for d in q.drugs if d not in current]
    if not planned or not (current or patient_context):
        return []
    result = safety_screen.screen(planned, current, patient_context)
    if not result.flags:
        return []
    top = result.flags[0]
    plural = "s" if len(result.flags) != 1 else ""
    return [ToolCard("safety_screen", f"Medication safety screen: {len(result.flags)} flag{plural}",
                     f"{top.title}. {top.message}", result.as_dict(), top.source_url, result.note,
                     severity=top.severity)]


def route(question: str, patient_context: str | None = None, is_anaphylaxis: bool = False) -> list[ToolCard]:
    """Run every deterministic tool the question calls for and return the cards in display order."""
    q = extract(question)
    cards = [
        *_adrenaline_cards(q, is_anaphylaxis),
        *_screen_cards(q, patient_context),
        *_regimen_cards(q),
        *_local_anaesthetic_cards(q),
    ]
    return cards
