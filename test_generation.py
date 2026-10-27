import pytest

from backend.app.domain import Chunk, RetrievedChunk, SourceType
from backend.app.generation.citations import ABSTAIN_MESSAGE, validate


def _source(text: str) -> RetrievedChunk:
    chunk = Chunk(chunk_id="c1", doc_id="d1", text=text, title="T", url="u", source="seed",
                  source_type=SourceType.UK_GUIDELINE)
    return RetrievedChunk(chunk=chunk)


def test_invalid_citations_removed_and_coverage_computed():
    report = validate("Give amoxicillin 500 mg three times daily [1]. It is effective [7].",
                      [_source("amoxicillin 500 mg three times daily")])
    assert report.invalid_ids == [7]
    assert "[7]" not in report.text
    assert report.cited_ids == [1]


def test_hallucinated_dose_is_detected():
    report = validate("Give amoxicillin 750 mg three times daily [1].", [_source("amoxicillin 500 mg")])
    assert "750 mg" in report.unsupported_numbers
    assert not report.grounded


def test_abstention_token_maps_to_safe_message():
    report = validate("INSUFFICIENT_EVIDENCE", [_source("x")])
    assert report.abstained and report.text == ABSTAIN_MESSAGE


@pytest.mark.asyncio
async def test_pipeline_end_to_end_grounded(pipeline):
    result = await pipeline.answer("What is the adult ibuprofen dose for dental pain?")
    assert not result.abstained
    assert result.sources
    assert "[" in result.answer
    assert not result.unsupported_numbers


@pytest.mark.asyncio
async def test_pipeline_declines_out_of_scope(pipeline):
    result = await pipeline.answer("Who won the football last night?")
    assert result.out_of_scope and not result.sources


@pytest.mark.asyncio
async def test_pipeline_emergency_banner_and_redaction(pipeline):
    result = await pipeline.answer("Mr John Smith collapsed with anaphylaxis, what adrenaline dose?")
    assert result.emergency_banner
    assert result.redactions.get("NAME") == 1


@pytest.mark.asyncio
async def test_stream_event_order(pipeline):
    events = [e["event"] async for e in pipeline.stream("fluoride toothpaste strength for a 4 year old")]
    assert events[0] == "meta"
    assert "sources" in events and events[-1] == "final"
    assert events.index("sources") < events.index("token")
