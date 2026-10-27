"""Prometheus metrics. Scraped at /metrics and visualised in Grafana."""

from __future__ import annotations

from typing import Any

from prometheus_client import Counter, Histogram

ANSWERS = Counter("rc_answers_total", "Answers produced", ["provider", "outcome"])
LATENCY = Histogram("rc_answer_latency_seconds", "End to end answer latency",
                    buckets=(0.25, 0.5, 1, 2, 4, 8, 16, 32))
COVERAGE = Histogram("rc_citation_coverage", "Share of factual sentences carrying a citation",
                     buckets=(0.2, 0.4, 0.6, 0.8, 0.9, 1.0))
EMERGENCIES = Counter("rc_emergency_triage_total", "Questions flagged as emergencies")
UNSUPPORTED = Counter("rc_unsupported_numbers_total", "Clinical figures not matched to a cited source")


def observe_answer(result: Any) -> None:
    outcome = "abstained" if result.abstained else ("grounded" if result.grounded else "ungrounded")
    ANSWERS.labels(result.provider, outcome).inc()
    LATENCY.observe(result.latency_ms / 1000)
    COVERAGE.observe(result.citation_coverage)
    if result.emergency_banner:
        EMERGENCIES.inc()
    if result.unsupported_numbers:
        UNSUPPORTED.inc(len(result.unsupported_numbers))
