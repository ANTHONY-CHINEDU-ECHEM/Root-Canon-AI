import pytest
from fastapi.testclient import TestClient

from backend.app.api.deps import Container
from backend.app.main import create_app


@pytest.fixture()
def client(settings, retriever, pipeline, monkeypatch):
    from backend.app.api.deps import LIMITER

    LIMITER.reset()
    monkeypatch.setattr(
        "backend.app.main.build_container",
        lambda _settings: Container(settings, retriever, pipeline, retriever.store, None),
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


HEADERS = {"X-API-Key": "change_me_local_key"}


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["chunks_indexed"] > 0


def test_ask_requires_key(client):
    assert client.post("/v1/ask", json={"question": "fluoride varnish for children"}).status_code == 401


def test_ask_returns_cited_answer(client):
    response = client.post("/v1/ask", headers=HEADERS,
                           json={"question": "How often should fluoride varnish be applied for children?"})
    body = response.json()
    assert response.status_code == 200
    assert body["sources"] and body["citation_coverage"] > 0


def test_search_with_filter(client):
    response = client.post("/v1/search", headers=HEADERS,
                           json={"query": "anticoagulant extraction", "filters": {"min_evidence_level": 6}})
    assert all(r["evidence_level"] == 6 for r in response.json()["results"])


def test_tools(client):
    assert client.post("/v1/tools/regimen", json={"drug": "metronidazole"}).json()["dose"] == "400 mg"
    la = client.post("/v1/tools/anaesthetic", json={"product": "articaine", "weight_kg": 70}).json()
    assert la["max_mg"] == 490.0
    assert client.get("/v1/tools/adrenaline", params={"age_years": 9}).json()["dose"].startswith("300")


def _events(text: str) -> list[tuple[str, dict]]:
    import json

    events = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        name, data = "message", []
        for line in block.splitlines():
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data.append(line[5:].strip())
        if data:
            events.append((name, json.loads("\n".join(data))))
    return events


def test_ready_and_security_headers(client):
    response = client.get("/ready")
    assert response.status_code == 200 and response.json()["ready"]
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Request-ID"]


def test_health_reports_provider_chain(client):
    body = client.get("/health").json()
    assert body["llm_chain"][0]["circuit"] == "closed"


def test_ask_includes_tool_cards_faithfulness_and_entities(client):
    body = client.post("/v1/ask", headers=HEADERS,
                       json={"question": "Amoxil dose for a dental abscess in a 3 year old"}).json()
    assert body["tool_cards"][0]["data"]["dose"] == "250 mg"
    assert body["entities"]["drugs"] == ["amoxicillin"] and body["entities"]["age_years"] == 3.0
    assert body["faithfulness"] is not None


def test_stream_emits_tools_before_sources(client):
    with client.stream("POST", "/v1/ask/stream", headers=HEADERS,
                       json={"question": "Patient on apixaban needs ibuprofen, what dose?"}) as response:
        names = [name for name, _ in _events("".join(response.iter_text()))]
    assert names[0] == "meta" and names[-1] == "final"
    assert names.index("tools") < names.index("sources") < names.index("token")


def test_understand_endpoint(client):
    body = client.post("/v1/understand", headers=HEADERS,
                       json={"question": "anaphylaxis in a 30 year old, adrenaline?"}).json()
    assert body["emergency"] == ["anaphylaxis"]
    assert body["tool_cards"][0]["tool"] == "adrenaline"


def test_screen_endpoint_flags_allergy(client):
    body = client.post("/v1/tools/screen", json={"planned": ["amoxicillin"], "current": ["Eliquis"],
                                                  "patient_context": "Mr Tom Hart, penicillin allergy"}).json()
    assert body["highest_severity"] == "contraindicated"
    assert body["current"] == ["apixaban"]


def test_feedback_and_admin_summary(client, settings, monkeypatch):
    ask = client.post("/v1/ask", headers=HEADERS, json={"question": "fluoride varnish frequency for children"})
    request_id = ask.json()["request_id"]
    recorded = client.post("/v1/feedback", headers=HEADERS,
                           json={"request_id": request_id, "rating": "down", "reasons": ["unclear"]})
    assert recorded.json()["recorded"]
    monkeypatch.setattr(settings, "admin_api_keys", ["admin-key"])
    assert client.get("/v1/audit/summary", headers=HEADERS).status_code == 403
    summary = client.get("/v1/audit/summary", headers={"X-API-Key": "admin-key"}).json()
    assert summary["answers"] >= 1 and summary["feedback"]["total"] >= 1


def test_knowledge_and_formulary_index(client):
    knowledge = client.get("/v1/knowledge").json()
    assert knowledge["supersession"]["rules"] and knowledge["formulary_reviewed"]
    formulary = client.get("/v1/tools/formulary").json()
    assert "amoxicillin" in formulary["regimens"] and "warfarin" in formulary["interaction_drugs"]


def test_tools_accept_brand_names(client):
    assert client.post("/v1/tools/regimen", json={"drug": "Flagyl"}).json()["drug"] == "metronidazole"
    checked = client.post("/v1/tools/interactions", json={"drugs": ["Flagyl", "Marevan"]}).json()
    assert checked["interactions"][0]["severity"] == "major"


def test_answer_cache_marks_hits(settings, retriever, pipeline, monkeypatch):
    from backend.app.cache import MemoryCache

    monkeypatch.setattr(
        "backend.app.main.build_container",
        lambda _settings: Container(settings, retriever, pipeline, retriever.store, MemoryCache()),
    )
    with TestClient(create_app(settings)) as client:
        body = {"question": "What is the adult ibuprofen dose for dental pain?"}
        first = client.post("/v1/ask", headers=HEADERS, json=body).json()
        second = client.post("/v1/ask", headers=HEADERS, json=body).json()
    assert not first["cached"] and second["cached"]
    assert first["answer"] == second["answer"]


def test_rate_limit_returns_retry_after(client, settings, monkeypatch):
    from backend.app.api.deps import LIMITER

    LIMITER.reset()
    monkeypatch.setattr(settings, "rate_limit_per_minute", 2)
    for _ in range(2):
        assert client.post("/v1/search", headers=HEADERS, json={"query": "fluoride"}).status_code == 200
    limited = client.post("/v1/search", headers=HEADERS, json={"query": "fluoride"})
    assert limited.status_code == 429 and int(limited.headers["Retry-After"]) >= 1
    LIMITER.reset()
