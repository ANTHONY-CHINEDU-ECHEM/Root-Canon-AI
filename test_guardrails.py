from backend.app.guardrails import emergency, pii, scope


def test_anaphylaxis_is_flagged_with_action():
    triage = emergency.assess("Patient after LA has swollen lips and is wheezing, possible anaphylaxis")
    assert triage.is_emergency
    assert "adrenaline" in triage.banner.lower()


def test_spreading_infection_airway_flagged():
    assert emergency.assess("swelling spreading to floor of mouth and difficulty swallowing").is_emergency


def test_routine_question_is_not_an_emergency():
    assert not emergency.assess("What recall interval should I set for a low risk adult?").is_emergency


def test_valid_nhs_number_redacted_but_random_digits_kept():
    # 943 476 5919 is the NHS Digital published example of a valid number.
    result = pii.redact("NHS number 943 476 5919, ref 1234567890")
    assert "[NHS_NUMBER]" in result.text
    assert "1234567890" in result.text


def test_contact_details_redacted():
    result = pii.redact("Mrs Patel, dob 12/03/1961, M40 5AB, 07700 900123, a.patel@example.com")
    for label in ("NAME", "DATE_OF_BIRTH", "POSTCODE", "PHONE", "EMAIL"):
        assert f"[{label}]" in result.text, label


def test_scope():
    assert scope.in_scope("Best antibiotic for a dental abscess?")
    assert not scope.in_scope("Write me a poem about the sea")
    assert scope.in_scope("What about in children?", history=["amoxicillin dose for dental abscess"])
