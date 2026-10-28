import pytest

from backend.app.domain import Chunk, RetrievedChunk, SourceType
from backend.app.generation.answerability import query_coverage
from backend.app.generation.faithfulness import LLMJudge, lexical_faithfulness
from backend.app.llm.base import LLMMessage, LLMProvider, LLMResponse
from backend.app.retrieval.bm25 import BM25Index


def _src(text: str, cid: str = "c1") -> RetrievedChunk:
    return RetrievedChunk(chunk=Chunk(chunk_id=cid, doc_id=cid, text=text, title="SDCEP", url="u", source="seed",
                                      source_type=SourceType.UK_GUIDELINE))


SOURCES = [_src("For adults the suggested regimen is amoxicillin 500 mg three times daily for 5 days."),
           _src("Metronidazole 400 mg three times daily for 3 days for necrotising periodontal disease.", "c2")]


def test_supported_claims_score_full():
    report = lexical_faithfulness("Adults take amoxicillin 500 mg three times daily for 5 days [1].", SOURCES)
    assert report.score == 1.0 and not report.unsupported


def test_claim_cited_to_the_wrong_source_is_unsupported():
    report = lexical_faithfulness("Metronidazole 400 mg three times daily for necrotising disease [1].", SOURCES)
    assert report.score == 0.0
    assert "metronidazole" in report.claims[0].missing_terms


def test_embellished_claim_is_caught():
    answer = ("Amoxicillin 500 mg three times daily [1]. "
              "It also eradicates osteomyelitis, prevents bacteraemia and replaces surgical drainage entirely [1].")
    report = lexical_faithfulness(answer, SOURCES)
    assert report.score == 0.5
    assert len(report.unsupported) == 1 and "osteomyelitis" in report.unsupported[0]


def test_uncited_sentences_are_ignored_by_faithfulness():
    assert lexical_faithfulness("Clinical judgement: consider allergy history.", SOURCES).score == 1.0


class _JudgeStub(LLMProvider):
    name = "stub"

    def __init__(self, text: str) -> None:
        self.text = text

    async def complete(self, system: str, messages: list[LLMMessage], *, temperature: float,
                       max_tokens: int) -> LLMResponse:
        assert "<claims>" in messages[0].content
        return LLMResponse(self.text, "stub", "stub")

    async def stream(self, *args, **kwargs):  # pragma: no cover - unused
        yield ""


@pytest.mark.asyncio
async def test_llm_judge_parses_verdicts_and_scores():
    judge = LLMJudge(_JudgeStub('Sure: {"verdicts": [{"claim": 1, "label": "partial", "reason": "x"}]}'))
    score, verdicts = await judge.judge("Amoxicillin 500 mg three times daily [1].", SOURCES)
    assert score == 0.5 and verdicts[0].label == "partial"


@pytest.mark.asyncio
async def test_llm_judge_tolerates_bad_json():
    judge = LLMJudge(_JudgeStub("I cannot comply"))
    assert await judge.judge("Amoxicillin 500 mg three times daily [1].", SOURCES) == (None, [])


def test_query_coverage_separates_covered_and_uncovered_questions():
    texts = [s.chunk.text for s in SOURCES]
    bm25 = BM25Index().build(["c1", "c2"], texts)
    covered = query_coverage("amoxicillin regimen for adults", SOURCES, bm25)
    uncovered = query_coverage("zirconia implant abutment torque", SOURCES, bm25)
    assert covered.coverage > 0.6
    assert uncovered.coverage == 0.0 and "zirconia" in uncovered.missing_terms


@pytest.mark.asyncio
async def test_pipeline_abstains_on_uncovered_topic(pipeline):
    result = await pipeline.answer("Recommended torque for a specific implant abutment screw brand?")
    assert result.abstained and result.retrieval["query_coverage"] < 0.2


@pytest.mark.asyncio
async def test_pipeline_reports_faithfulness(pipeline):
    result = await pipeline.answer("What is the adult ibuprofen dose for dental pain?")
    assert result.faithfulness is not None and result.faithfulness >= 0.5
    assert result.grounded
