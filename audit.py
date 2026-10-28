"""Audit trail and clinician feedback.

Every answer is recorded without patient text: the question is stored only as a
keyed hash (HMAC with a deployment secret, so common questions cannot be
recovered by hashing a dictionary of guesses), alongside the sources used, the
safety checks and the provider. Feedback is linked to an answer by its request
id, and any free text comment is redacted before it is written.

`summarise` turns both logs into the figures a clinical safety officer reviews:
abstention and grounding rates, coverage and faithfulness, emergencies, tool use,
superseded sources and the share of negative feedback.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import statistics
import time
from collections import Counter
from pathlib import Path
from threading import Lock
from typing import Any

from backend.app.guardrails import pii

_LOCK = Lock()


def question_hash(question: str, salt: str) -> str:
    return hmac.new(salt.encode(), question.strip().lower().encode(), hashlib.sha256).hexdigest()


class AuditLog:
    def __init__(self, directory: Path, salt: str) -> None:
        self.directory = directory
        self.salt = salt

    @property
    def answers_path(self) -> Path:
        return self.directory / "answers.jsonl"

    @property
    def feedback_path(self) -> Path:
        return self.directory / "feedback.jsonl"

    def _append(self, path: Path, record: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with _LOCK, path.open("a", encoding="utf-8") as handle:
            handle.write(line)

    def record_answer(self, result: Any, question: str) -> None:
        self._append(self.answers_path, {
            "request_id": result.request_id,
            "question_hmac": question_hash(question, self.salt),
            "sources": [s.url for s in result.sources],
            "superseded_sources": [s.url for s in result.sources if s.superseded_by],
            "abstained": result.abstained,
            "out_of_scope": result.out_of_scope,
            "grounded": result.grounded,
            "coverage": result.citation_coverage,
            "faithfulness": result.faithfulness,
            "unsupported_numbers": result.unsupported_numbers,
            "emergency": bool(result.emergency_banner),
            "tools": [c["tool"] for c in result.tool_cards],
            "safety_flags": [f["severity"] for c in result.tool_cards if c["tool"] == "safety_screen"
                             for f in c["data"].get("flags", [])],
            "provider": result.provider,
            "model": result.model,
            "latency_ms": result.latency_ms,
            "ts": time.time(),
        })

    def record_feedback(self, request_id: str, rating: str, reasons: list[str], comment: str | None) -> dict:
        redaction = pii.redact(comment) if comment else None
        record = {
            "request_id": request_id,
            "rating": rating,
            "reasons": reasons,
            "comment": redaction.text if redaction else None,
            "comment_redactions": redaction.found if redaction else {},
            "ts": time.time(),
        }
        self._append(self.feedback_path, record)
        return record

    @staticmethod
    def _read(path: Path, since: float | None) -> list[dict]:
        if not path.exists():
            return []
        rows = []
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if since is None or row.get("ts", 0) >= since:
                        rows.append(row)
        return rows

    def summarise(self, since: float | None = None) -> dict:
        answers = self._read(self.answers_path, since)
        feedback = self._read(self.feedback_path, since)
        answered = [a for a in answers if not a.get("abstained") and not a.get("out_of_scope")]

        def rate(rows: list[dict], key: str) -> float:
            return round(sum(bool(r.get(key)) for r in rows) / len(rows), 3) if rows else 0.0

        def mean(rows: list[dict], key: str) -> float | None:
            values = [r[key] for r in rows if isinstance(r.get(key), int | float)]
            return round(statistics.mean(values), 3) if values else None

        latencies = sorted(a["latency_ms"] for a in answers if "latency_ms" in a)
        ratings = Counter(f["rating"] for f in feedback)
        return {
            "answers": len(answers),
            "answered": len(answered),
            "abstention_rate": rate(answers, "abstained"),
            "out_of_scope_rate": rate(answers, "out_of_scope"),
            "grounded_rate": rate(answered, "grounded"),
            "mean_citation_coverage": mean(answered, "coverage"),
            "mean_faithfulness": mean(answered, "faithfulness"),
            "answers_with_unsupported_figures": sum(bool(a.get("unsupported_numbers")) for a in answers),
            "emergencies": sum(bool(a.get("emergency")) for a in answers),
            "answers_citing_superseded_guidance": sum(bool(a.get("superseded_sources")) for a in answers),
            "tool_cards": dict(Counter(t for a in answers for t in a.get("tools", []))),
            "safety_flags": dict(Counter(s for a in answers for s in a.get("safety_flags", []))),
            "providers": dict(Counter(a.get("provider", "unknown") for a in answers)),
            "latency_ms_p50": latencies[len(latencies) // 2] if latencies else None,
            "latency_ms_p95": latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))] if latencies else None,
            "feedback": {"total": len(feedback), **ratings,
                         "negative_rate": round(ratings.get("down", 0) / len(feedback), 3) if feedback else 0.0,
                         "reasons": dict(Counter(r for f in feedback for r in f.get("reasons", [])))},
        }
