import pytest

from backend.app.domain import Chunk, RetrievedChunk, SourceType
from backend.app.generation.prompts import format_sources
from backend.app.retrieval.supersession import SupersessionGraph, default_graph


def _chunk(title: str, year: int | None, publisher: str | None = None, url: str = "https://example.org") -> Chunk:
    return Chunk(chunk_id=f"{title}{year}", doc_id=f"{title}{year}", text="Guidance text.", title=title, url=url,
                 source="seed", source_type=SourceType.UK_GUIDELINE, published_year=year, publisher=publisher,
                 jurisdiction="UK")


def test_default_graph_loads_and_validates():
    graph = default_graph()
    assert {r.id for r in graph.rules} >= {"dboh-third-edition", "rcuk-anaphylaxis-2008"}


def test_old_edition_is_superseded_but_current_is_not():
    graph = default_graph()
    assert graph.find(_chunk("Delivering better oral health: fluoride", 2017)) is not None
    assert graph.find(_chunk("Delivering better oral health: Chapter 9 fluoride", 2021)) is None


def test_undated_documents_are_not_assumed_superseded():
    assert default_graph().find(_chunk("Delivering better oral health", None)) is None


def test_publisher_condition_is_respected():
    graph = default_graph()
    assert graph.find(_chunk("Anaphylaxis algorithm", 2008, "Resuscitation Council UK")) is not None
    assert graph.find(_chunk("Anaphylaxis case report", 2008, "Some journal")) is None


def test_annotate_demotes_and_labels():
    item = RetrievedChunk(chunk=_chunk("Delivering better oral health", 2014), final_score=0.8)
    assert default_graph().annotate(item)
    assert item.final_score == pytest.approx(0.4)
    assert item.superseded_by["title"].startswith("Delivering better oral health, 4th edition")


def test_chains_resolve_to_newest():
    graph = SupersessionGraph.from_config({"rules": [
        {"id": "a", "match": {"title_contains": "alpha"}, "superseded_by": {"id": "b", "title": "B", "url": "u/b"}},
        {"id": "b", "match": {"title_contains": "beta"}, "superseded_by": {"id": "c", "title": "C", "url": "u/c"}},
    ]})
    assert graph.resolve(graph.find(_chunk("alpha guidance", 2010))).title == "C"


def test_cycles_and_unknown_keys_are_rejected():
    with pytest.raises(ValueError, match="cycle"):
        SupersessionGraph.from_config({"rules": [
            {"id": "a", "match": {"doc_id": "x"}, "superseded_by": {"id": "b", "title": "B", "url": "u"}},
            {"id": "b", "match": {"doc_id": "y"}, "superseded_by": {"id": "a", "title": "A", "url": "u"}},
        ]})
    with pytest.raises(ValueError, match="unknown match keys"):
        SupersessionGraph.from_config({"rules": [
            {"id": "a", "match": {"colour": "red"}, "superseded_by": {"id": "b", "title": "B", "url": "u"}}]})


def test_prompt_marks_superseded_sources():
    item = RetrievedChunk(chunk=_chunk("Delivering better oral health", 2014), final_score=0.8)
    default_graph().annotate(item)
    assert 'superseded="true"' in format_sources([item])


def test_retriever_demotes_superseded_guidance(retriever):
    old = _chunk("Delivering better oral health: fluoride toothpaste", 2014)
    old = old.model_copy(update={"text": "Fluoride toothpaste 1,450 ppm for children over 3 and adults."})
    results, trace = retriever.retrieve("fluoride toothpaste ppm children")
    baseline_top = results[0].chunk.doc_id
    retriever.store.upsert([old], retriever.embedder.embed_documents([old.text]))
    try:
        results, trace = retriever.retrieve("fluoride toothpaste ppm children")
        superseded = [r for r in results if r.superseded_by]
        assert results[0].chunk.doc_id == baseline_top
        assert trace.superseded >= 1
        assert all(r.chunk.doc_id == old.doc_id for r in superseded)
        # With a wide window the withdrawn edition is still visible, but labelled and below current guidance.
        wide, _ = retriever.retrieve("fluoride toothpaste ppm children", top_k=40)
        positions = {r.chunk.doc_id: i for i, r in enumerate(wide)}
        assert old.doc_id in positions and wide[positions[old.doc_id]].superseded_by
        assert positions["seed:dboh-fluoride"] < positions[old.doc_id]
    finally:
        # The retriever fixture is session scoped, so remove the synthetic chunk again.
        assert retriever.store.delete([old.chunk_id]) == 1
