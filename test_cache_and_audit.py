import json

from backend.app.audit import AuditLog, question_hash
from backend.app.cache import MemoryCache, build_cache, cache_key


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_memory_cache_expiry_and_lru_eviction():
    clock = Clock()
    cache = MemoryCache(max_entries=2, clock=clock)
    cache.set("a", "1", ttl_seconds=10)
    cache.set("b", "2", ttl_seconds=10)
    assert cache.get("a") == "1"          # a is now most recently used
    cache.set("c", "3", ttl_seconds=10)   # evicts b
    assert cache.get("b") is None and cache.get("c") == "3"
    clock.now += 11
    assert cache.get("a") is None


def test_cache_key_is_stable_and_order_independent_for_dicts():
    assert cache_key("q", {"a": 1, "b": 2}) == cache_key("q", {"b": 2, "a": 1})
    assert cache_key("q1") != cache_key("q2")


def test_build_cache_falls_back_to_memory_without_redis():
    cache = build_cache("redis://127.0.0.1:1/0", memory_size=8)
    assert cache is not None and cache.backend == "memory"
    assert build_cache(None, memory_size=0) is None


def test_question_hash_is_keyed():
    assert question_hash("Amoxicillin dose?", "salt-a") != question_hash("Amoxicillin dose?", "salt-b")
    assert question_hash(" amoxicillin DOSE? ", "s") == question_hash("amoxicillin dose?", "s")


async def test_audit_records_answers_without_question_text(pipeline):
    result = await pipeline.answer("Mrs Ada Jones needs amoxicillin dose for a dental abscess in a 3 year old")
    rows = [json.loads(line) for line in pipeline.audit.answers_path.read_text().splitlines()]
    row = next(r for r in rows if r["request_id"] == result.request_id)
    assert "question" not in row and len(row["question_hmac"]) == 64
    assert row["tools"] == ["regimen"]
    assert "Jones" not in pipeline.audit.answers_path.read_text()


def test_feedback_comment_is_redacted_and_summarised(tmp_path):
    audit = AuditLog(tmp_path, "salt")
    record = audit.record_feedback("req-123456", "down", ["outdated"], "Mr John Smith 07700 900123 says wrong")
    assert "[NAME]" in record["comment"] and "[PHONE]" in record["comment"]
    audit.record_feedback("req-abcdef", "up", ["helpful"], None)
    summary = audit.summarise()
    assert summary["feedback"]["total"] == 2
    assert summary["feedback"]["negative_rate"] == 0.5
    assert summary["feedback"]["reasons"] == {"outdated": 1, "helpful": 1}


def test_summary_handles_empty_and_corrupt_logs(tmp_path):
    audit = AuditLog(tmp_path, "salt")
    assert audit.summarise()["answers"] == 0
    audit.answers_path.parent.mkdir(parents=True, exist_ok=True)
    audit.answers_path.write_text('{"abstained": true, "ts": 1}\nnot json\n')
    summary = audit.summarise()
    assert summary["answers"] == 1 and summary["abstention_rate"] == 1.0
