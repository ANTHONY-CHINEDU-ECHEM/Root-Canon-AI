import pytest

from backend.app.clinical.entities import extract, normalise


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Patient on Eliquis", "Patient on apixaban"),
        ("takes Xarelto and Nurofen", "takes rivaroxaban and ibuprofen"),
        ("pen V for an abscess", "phenoxymethylpenicillin for an abscess"),
        ("Pediatric anesthetic hemorrhage", "Paediatric anaesthetic haemorrhage"),
        ("epinephrine for anaphylaxis", "adrenaline for anaphylaxis"),
        ("lignocaine 2%", "lidocaine 2%"),
    ],
)
def test_normalise_brands_and_spelling(text, expected):
    assert normalise(text) == expected


def test_normalise_leaves_clinical_tokens_untouched():
    text = "Lidocaine 2% with adrenaline 1:80,000, 1,450 ppm toothpaste"
    assert normalise(text) == text


@pytest.mark.parametrize(
    ("text", "age"),
    [
        ("Amoxicillin dose for a 3 year old", 3.0),
        ("a 3-year-old with an abscess", 3.0),
        ("45yo with asthma", 45.0),
        ("18-month-old infant", 1.5),
        ("child aged 7 with toothache", 7.0),
        ("baby aged 9 months", 0.75),
    ],
)
def test_age_extraction(text, age):
    assert extract(text).age_years == age


@pytest.mark.parametrize(
    "text",
    [
        "taking alendronic acid for 6 years, extraction?",  # a duration, not an age
        "amoxicillin 500 mg three times daily for 5 days",
        "review in 3 months",
    ],
)
def test_durations_are_not_mistaken_for_age(text):
    assert extract(text).age_years is None


def test_weight_drugs_classes_and_intents():
    q = extract("Max articaine for a 22 kg child on Xarelto, any interaction with ibuprofen?")
    assert q.weight_kg == 22.0
    assert q.drugs == ("articaine", "rivaroxaban", "ibuprofen")
    assert {"local_anaesthetics", "doacs", "nsaids"} <= q.classes
    assert {"maximum_dose", "interaction"} <= q.intents
    assert q.mentions_child


def test_expansion_only_adds_generics_not_already_present():
    q = extract("Patient on Eliquis needs an extraction")
    assert q.expansion == "apixaban"
    assert extract("Patient on apixaban needs an extraction").expansion == ""


def test_maxillary_is_not_a_maximum_dose_intent():
    assert "maximum_dose" not in extract("maxillary molar extraction").intents
