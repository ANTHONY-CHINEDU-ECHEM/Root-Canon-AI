import pytest

from evaluation.run_eval import check_gate, evaluate, load_golden, offline_pipeline, offline_settings, to_markdown


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    import asyncio

    pipeline = offline_pipeline(offline_settings(tmp_path_factory.mktemp("eval")))
    return asyncio.run(evaluate(pipeline))


def test_golden_set_is_well_formed():
    rows = load_golden()
    assert len({r["id"] for r in rows}) == len(rows) >= 30
    for row in rows:
        assert {"question", "expected_doc", "expected_facts", "should_abstain", "emergency"} <= row.keys()
        if row["should_abstain"] or row.get("expected_out_of_scope"):
            assert row["expected_doc"] is None


def test_offline_baseline_passes_the_ci_gate(report):
    import yaml

    from evaluation.run_eval import THRESHOLDS

    assert check_gate(report, yaml.safe_load(THRESHOLDS.read_text())) == []
    assert report["tool_routing_accuracy"] == 1.0 and report["scope_accuracy"] == 1.0


def test_gate_reports_regressions():
    failures = check_gate({"retrieval_hit_at_5": 0.5, "unsupported_rate": 0.1},
                          {"min": {"retrieval_hit_at_5": 0.9, "faithfulness": 0.9}, "max": {"unsupported_rate": 0}})
    assert len(failures) == 3 and any("faithfulness = None" in f for f in failures)


def test_markdown_report(report):
    text = to_markdown(report, ["x is below"])
    assert text.startswith("# Root Canon AI evaluation") and "| retrieval_hit_at_5 |" in text and "Failed:" in text
