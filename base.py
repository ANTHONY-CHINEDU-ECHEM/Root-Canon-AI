"""Base class for all source connectors.

Connectors are polite by construction: every request goes through a shared
rate limiter, retries with exponential backoff on transient errors, identifies
itself with a descriptive User Agent, and honours robots.txt for HTML sources.
"""

from __future__ import annotations

import abc
import asyncio
import time
from collections.abc import AsyncIterator
from urllib import robotparser
from urllib.parse import urlparse

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from backend.app.domain import SourceDocument
from backend.app.logging_setup import get_logger

USER_AGENT = "RootCanonAI/1.0 (+https://github.com/ANTHONY-CHINEDU-ECHEM/RootCanonAI; research ingestion)"


class TransientHTTPError(Exception):
    """Raised for 429 and 5xx responses so tenacity can retry them."""


class RateLimiter:
    """Simple async token bucket: at most `rate` requests per second."""

    def __init__(self, rate: float) -> None:
        self._interval = 1.0 / rate
        self._lock = asyncio.Lock()
        self._next = 0.0

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            if now < self._next:
                await asyncio.sleep(self._next - now)
            self._next = max(now, self._next) + self._interval


class SourceConnector(abc.ABC):
    name: str = "base"
    requests_per_second: float = 3.0
    respect_robots: bool = False

    def __init__(self, client: httpx.AsyncClient | None = None, **options: object) -> None:
        self._client = client or httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT}, timeout=httpx.Timeout(45.0), follow_redirects=True
        )
        self._limiter = RateLimiter(self.requests_per_second)
        self._robots: dict[str, robotparser.RobotFileParser] = {}
        self.options = options
        self.log = get_logger(f"ingestion.{self.name}")

    async def __aenter__(self) -> SourceConnector:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._client.aclose()

    async def _allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        if base not in self._robots:
            parser = robotparser.RobotFileParser()
            try:
                response = await self._client.get(f"{base}/robots.txt")
                parser.parse(response.text.splitlines() if response.status_code == 200 else [])
            except httpx.HTTPError:
                parser.parse([])
            self._robots[base] = parser
        return self._robots[base].can_fetch(USER_AGENT, url)

    async def get(self, url: str, **kwargs: object) -> httpx.Response:
        if not await self._allowed(url):
            raise PermissionError(f"robots.txt disallows {url}")
        async for attempt in AsyncRetrying(
            retry=retry_if_exception_type((TransientHTTPError, httpx.TransportError)),
            wait=wait_exponential_jitter(initial=1, max=30),
            stop=stop_after_attempt(6),
            reraise=True,
        ):
            with attempt:
                await self._limiter.wait()
                response = await self._client.get(url, **kwargs)  # type: ignore[arg-type]
                if response.status_code == 429 or response.status_code >= 500:
                    raise TransientHTTPError(f"{response.status_code} for {url}")
                response.raise_for_status()
                return response
        raise RuntimeError("unreachable")

    @abc.abstractmethod
    def fetch(self, limit: int | None = None) -> AsyncIterator[SourceDocument]:
        """Yield normalised SourceDocuments, at most `limit` of them."""
