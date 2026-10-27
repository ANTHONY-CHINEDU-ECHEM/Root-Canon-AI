"""Medical emergency detection.

Runs before retrieval on every question. When a pattern describing a live
emergency is found, the response is prefixed with an unmissable action banner
(call 999, start the Resuscitation Council UK ABCDE approach) and the relevant
emergency guidance is pinned to the top of the evidence. The assistant never
delays an emergency answer behind generation latency: the banner is returned
in the first streamed event.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class EmergencyRule:
    code: str
    title: str
    patterns: tuple[str, ...]
    action: str
    retrieval_hint: str


RULES: tuple[EmergencyRule, ...] = (
    EmergencyRule(
        "anaphylaxis", "Suspected anaphylaxis",
        (r"anaphyla", r"(throat|tongue|lip)s?\b.{0,25}\b(swell|swollen|tight)", r"hives?.{0,40}(wheez|breath)",
         r"allergic reaction.{0,40}(breath|wheez|collaps|faint)"),
        "Call 999. Lie the patient flat with legs raised (sit up if breathing is difficult). Give adrenaline "
        "1:1000 intramuscularly into the anterolateral thigh at the dose for age, and repeat after 5 minutes "
        "if there is no improvement. Give high flow oxygen.",
        "anaphylaxis adrenaline intramuscular dose dental practice",
    ),
    EmergencyRule(
        "cardiac_arrest", "Collapse, unresponsive or not breathing normally",
        (r"cardiac arrest", r"not breathing", r"no pulse", r"unresponsive", r"collapsed?\b.{0,30}(not|isn'?t) (breathing|responding)"),
        "Call 999 and request an AED. Start CPR at 30 compressions to 2 breaths and attach the AED as soon as it arrives.",
        "cardiac arrest basic life support AED dental practice",
    ),
    EmergencyRule(
        "airway", "Airway obstruction or choking",
        (r"chok(e|ing)", r"inhal(ed|ation) of (a |an )?(crown|instrument|file|tooth|object)", r"airway (obstruct|block)",
         r"swallowed (a |an )?(crown|bur|file|instrument|reamer)"),
        "Encourage coughing if effective. If ineffective and conscious: up to 5 back blows then up to 5 abdominal "
        "thrusts. If the patient becomes unresponsive, call 999 and start CPR.",
        "choking airway obstruction management dental",
    ),
    EmergencyRule(
        "cardiac_chest_pain", "Chest pain of possible cardiac origin",
        (r"chest pain", r"angina", r"crushing (pain|pressure)", r"heart attack", r"myocardial infarction"),
        "Stop treatment. Give glyceryl trinitrate spray sublingually. If pain is not relieved, call 999 and give "
        "aspirin 300 mg dispersible to chew unless allergic.",
        "angina myocardial infarction glyceryl trinitrate aspirin dental emergency",
    ),
    EmergencyRule(
        "seizure", "Prolonged or repeated seizure",
        (r"seizure", r"fitting", r"convuls", r"status epilepticus"),
        "Protect from injury, do not restrain. If convulsion lasts 5 minutes or longer, give buccal midazolam at "
        "the dose for age and call 999.",
        "epileptic seizure buccal midazolam dental emergency",
    ),
    EmergencyRule(
        "hypoglycaemia", "Suspected hypoglycaemia",
        (r"hypo(glyc|\b)", r"low (blood )?sugar", r"diabetic.{0,30}(confused|drowsy|sweat|shak)"),
        "If cooperative, give 15 to 20 g of quick acting oral glucose. If unable to swallow safely, give glucagon "
        "1 mg intramuscularly and call 999.",
        "hypoglycaemia oral glucose glucagon dental emergency",
    ),
    EmergencyRule(
        "spreading_infection", "Spreading odontogenic infection threatening the airway",
        (r"(swelling|cellulitis).{0,60}(eye|floor of (the )?mouth|neck|difficulty (breathing|swallowing))",
         r"ludwig", r"trismus.{0,40}(fever|swallow|breath)", r"can'?t (swallow|breathe)"),
        "Treat as an emergency. Arrange same day referral to oral and maxillofacial surgery or the emergency "
        "department. Signs of airway compromise require a 999 call.",
        "spreading dental infection airway urgent referral cellulitis",
    ),
    EmergencyRule(
        "haemorrhage", "Uncontrolled bleeding",
        (r"(won'?t|will not|cannot|can'?t) stop bleeding", r"uncontrolled (bleed|haemorrhage)", r"heavy bleeding after extraction"),
        "Apply firm pressure with a damp gauze pack for at least 10 minutes, consider local haemostatic measures "
        "and sutures. Seek urgent help if bleeding persists or the patient is anticoagulated and unstable.",
        "post extraction haemorrhage local haemostatic measures anticoagulant",
    ),
)

_COMPILED = [(rule, [re.compile(p, re.IGNORECASE) for p in rule.patterns]) for rule in RULES]


@dataclass(frozen=True)
class EmergencyAssessment:
    is_emergency: bool
    rules: tuple[EmergencyRule, ...] = ()

    @property
    def banner(self) -> str | None:
        if not self.is_emergency:
            return None
        return " ".join(f"{r.title}: {r.action}" for r in self.rules)

    @property
    def retrieval_hint(self) -> str:
        return " ".join(r.retrieval_hint for r in self.rules)


def assess(question: str) -> EmergencyAssessment:
    matched = tuple(rule for rule, patterns in _COMPILED if any(p.search(question) for p in patterns))
    return EmergencyAssessment(bool(matched), matched)
