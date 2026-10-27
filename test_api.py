import pytest
from fastapi.testclient import TestClient

from backend.app.api.deps import Container
from backend.app.main import create_app


@pytest.fixture()
def client(settings, retriever, pipeline, monkeypatch):
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
