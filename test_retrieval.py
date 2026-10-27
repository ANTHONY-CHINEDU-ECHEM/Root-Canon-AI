from backend.app.retrieval.bm25 import BM25Index, tokenize
from backend.app.retrieval.hybrid import recency_score, reciprocal_rank_fusion


def test_tokenizer_keeps_clinical_quantities_and_expands_abbreviations():
    tokens = tokenize("Give 500 mg amoxicillin; toothpaste 1,450 ppm; MRONJ risk")
    assert "500mg" in tokens
    assert "1450ppm" in tokens
    assert "osteonecrosis" in tokens


def test_bm25_ranks_exact_drug_match_first():
    index = BM25Index().build(
        ["a", "b", "c"],
        ["metronidazole 400 mg three times daily", "paracetamol 1 g four times daily", "fluoride varnish"],
    )
    assert index.search("metronidazole dose")[0][0] == "a"


def test_rrf_rewards_agreement_between_rankers():
    fused = reciprocal_rank_fusion([["x", "y", "z"], ["y", "x", "q"]])
    assert fused["x"] == fused["y"] > fused["z"]


def test_recency_decays():
    assert recency_score(2026, 8, today=2026) > recency_score(2010, 8, today=2026)


def test_hybrid_retrieves_correct_guidance(retriever):
    results, trace = retriever.retrieve("recall interval for an adult oral health review")
    assert results[0].chunk.title.startswith("NICE CG19")
    assert trace.returned > 0


def test_hybrid_prefers_uk_guidance_for_anticoagulant_question(retriever):
    results, _ = retriever.retrieve("patient on apixaban needs an extraction, should they miss a dose")
    assert "anticoagulants" in results[0].chunk.title.lower()


def test_filters_restrict_source_type(retriever):
    results, _ = retriever.retrieve("infective endocarditis prophylaxis",
                                    filters={"source_type": ["narrative_review"]})
    assert results and all(r.chunk.source_type.value == "narrative_review" for r in results)


def test_per_document_cap(retriever):
    results, _ = retriever.retrieve("fluoride toothpaste varnish ppm children adults", top_k=8)
    counts = {}
    for r in results:
        counts[r.chunk.doc_id] = counts.get(r.chunk.doc_id, 0) + 1
    assert max(counts.values()) <= 2
