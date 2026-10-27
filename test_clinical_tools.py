import pytest

from backend.app.clinical import tools


def test_adult_amoxicillin():
    result = tools.lookup_regimen("amoxicillin")
    assert result.dose == "500 mg" and result.frequency == "three times daily"
    assert result.source_url.startswith("https://sdcepdentalprescribing.nhs.scot")


def test_paediatric_amoxicillin_band():
    assert tools.lookup_regimen("amoxicillin", age_years=3).dose == "250 mg"
    assert tools.lookup_regimen("amoxicillin", age_years=0.75).dose == "125 mg"


def test_child_without_band_refuses():
    with pytest.raises(ValueError):
        tools.lookup_regimen("ibuprofen", age_years=4)


def test_adrenaline_by_age():
    assert tools.adrenaline_dose(30)["dose"].startswith("500 micrograms")
    assert tools.adrenaline_dose(8)["dose"].startswith("300 micrograms")
    assert tools.adrenaline_dose(3)["dose"].startswith("150 micrograms")


def test_local_anaesthetic_ceiling_applies():
    small = tools.local_anaesthetic_max("lidocaine", 20)
    assert small.max_mg == 88.0
    large = tools.local_anaesthetic_max("lidocaine", 120)
    assert large.max_mg == 300.0  # absolute ceiling, not 528 mg


def test_interactions_sorted_by_severity():
    hits = tools.check_interactions(["Metronidazole", "warfarin", "amoxicillin"])
    assert hits[0]["severity"] == "major"
    assert {h["a"] for h in hits} == {"metronidazole", "amoxicillin"}
