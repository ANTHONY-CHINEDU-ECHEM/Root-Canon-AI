"""Answer cache.

Redis is used when it is reachable so every API replica shares the cache. When
it is not, a bounded in process LRU with per entry expiry takes over, which
keeps single instance and development deployments fast without a dependency.

Only redacted, grounded, non emergency answers are cached (the routes decide
that), and keys are hashes of the redacted request, so no patient identifier
can appear in a cache key or value.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict
from threading import Lock
from typing import Protocol

from backend.app.logging_setup import get_logger
from backend.app.observability import metrics

log = get_logger("cache")


class AnswerCache(Protocol):
    backend: str

    def get(self, key: str) -> str | None: ...

    def set(self, key: str, value: str, ttl_seconds: int) -> None: ...


def cache_key(*parts: object) -> str:
    return "rc:answer:v2:" + hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


class MemoryCache:
    backend = "memory"

    def __init__(self, max_entries: int = 512, clock=time.monotonic) -> None:  # type: ignore[no-untyped-def]
        self.max_entries = max_entries
        self._clock = clock
        self._data: OrderedDict[str, tuple[float, str]] = OrderedDict()
        self._lock = Lock()

    def get(self, key: str) -> str | None:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                metrics.CACHE.labels("miss").inc()
                return None
            expires, value = item
            if expires < self._clock():
                del self._data[key]
                metrics.CACHE.labels("expired").inc()
                return None
            self._data.move_to_end(key)
            metrics.CACHE.labels("hit").inc()
            return value

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        with self._lock:
            self._data[key] = (self._clock() + ttl_seconds, value)
            self._data.move_to_end(key)
            while len(self._data) > self.max_entries:
                self._data.popitem(last=False)

    def __len__(self) -> int:
        return len(self._data)


class RedisCache:
    backend = "redis"

    def __init__(self, client) -> None:  # type: ignore[no-untyped-def]
        self.client = client

    def get(self, key: str) -> str | None:
        try:
            value = self.client.get(key)
        except Exception as exc:
            log.warning("cache_get_failed", error=str(exc))
            return None
        metrics.CACHE.labels("hit" if value else "miss").inc()
        return value.decode() if isinstance(value, bytes) else value

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        try:
            self.client.setex(key, ttl_seconds, value)
        except Exception as exc:
            log.warning("cache_set_failed", error=str(exc))


def build_cache(redis_url: str | None, memory_size: int = 512) -> AnswerCache | None:
    if memory_size <= 0 and not redis_url:
        return None
    if redis_url:
        try:
            import redis

            client = redis.Redis.from_url(redis_url, socket_connect_timeout=1, socket_timeout=1)
            client.ping()
            return RedisCache(client)
        except Exception as exc:
            log.info("redis_unavailable_using_memory_cache", error=str(exc))
    return MemoryCache(memory_size) if memory_size > 0 else None
