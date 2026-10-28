from backend.app.clinical import safety_screen
from backend.app.clinical.router import route


def _tools(cards):
    return [c.tool for c in cards]


def test_paediatric_regimen_card_uses_age_band():
    [card] = route("Amoxicillin dose for a dental abscess in a 3 year old")
    assert card.tool == "regimen"
    assert card.data["dose"] == "250 mg"
    assert card.source_url.startswith("https://sdcepdentalprescribing.nhs.scot")


def test_brand_name_routes_to_generic_regimen():
    [card] = route("How much Flagyl for necrotising gingivitis?")
    assert card.data["drug"] == "metronidazole" and card.data["dose"] == "400 mg"


def test_child_without_age_never_gets_an_adult_dose():
    [card] = route("amoxicillin dose for a child with an abscess")
    assert card.severity == "caution"
    assert "500 mg" not in card.summary and "age" in card.summary.lower()


def test_child_outside_formulary_bands_is_refused():
    [card] = route("ibuprofen dose for a 4 year old")
    assert card.severity == "caution" and "BNFC" in card.summary


def test_no_dose_intent_no_regimen_card():
    assert route("Is amoxicillin better absorbed than phenoxymethylpenicillin?") == []


def test_local_anaesthetic_ceiling_card():
    [card] = route("max articaine for a 22 kg child")
    assert card.tool == "local_anaesthetic"
    assert card.data["max_mg"] == 154.0


def test_anaphylaxis_card_with_and_without_age():
    [card] = route("anaphylaxis in an 8 year old", is_anaphylaxis=True)
    assert card.data["dose"].startswith("300 micrograms") and card.severity == "emergency"
    [bands] = route("suspected anaphylaxis", is_anaphylaxis=True)
    assert len(bands.data["age_bands"]) == 3


def test_patient_medicine_in_question_triggers_screen_first():
    cards = route("Patient on apixaban needs ibuprofen for pain, dose?")
    assert _tools(cards) == ["safety_screen", "regimen"]
    screen = cards[0]
    assert screen.severity == "major"
    assert any(f["rule_id"] == "anticoagulated" for f in screen.data["flags"])


def test_patient_context_allergy_is_contraindication():
    cards = route("amoxicillin dose", "Penicillin allergy (rash). Takes warfarin.")
    assert cards[0].tool == "safety_screen" and cards[0].severity == "contraindicated"


def test_screen_orders_by_severity_and_deduplicates():
    result = safety_screen.screen(["ibuprofen", "metronidazole"], ["warfarin"], "asthma, drinks alcohol")
    severities = [f.severity for f in result.flags]
    assert severities == sorted(severities, key=lambda s: safety_screen.SEVERITY_ORDER[s])
    titles = [f.title for f in result.flags]
    assert len(titles) == len(set(titles))
    assert result.highest_severity == "major"


def test_screen_with_no_findings_says_so_honestly():
    result = safety_screen.screen(["paracetamol"], ["simvastatin"])
    assert result.flags == [] and "not proof of safety" in result.note


def test_screen_accepts_brand_names():
    result = safety_screen.screen(["Nurofen"], ["Xarelto"])
    assert result.planned == ["ibuprofen"] and result.current == ["rivaroxaban"]
    assert any(f.kind == "interaction" for f in result.flags)
