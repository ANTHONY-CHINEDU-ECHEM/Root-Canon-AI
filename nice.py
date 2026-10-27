"""NICE Syndication API connector.

NICE content is licensed for reuse through the NICE Syndication service. A free
licence key is required for most non commercial uses; set
NICE_SYNDICATION_API_KEY. Without a key the connector logs a clear message and
yields nothing rather than scraping.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import date

from backend.app.domain import Licence, SourceDocument, SourceType
from ingestion.sources.base import SourceConnector
from ingestion.sources.govuk import html_to_sections

API = "https://api.nice.org.uk/services/guidance/structured-documents"


class NICESyndicationConnector(SourceConnector):
    name = "nice"
    requests_per_second = 2.0

    def __init__(self, guidance_ids: list[str], **options: object) -> None:
        super().__init__(**options)
        self.guidance_ids = guidance_ids
        self.api_key = os.getenv("NICE_SYNDICATION_API_KEY")

    async def fetch(self, limit: int | None = None) -> AsyncIterator[SourceDocument]:
        if not self.api_key:
            self.log.warning("nice_skipped", reason="NICE_SYNDICATION_API_KEY not set")
            return
        headers = {"API-Key": self.api_key, "Accept": "application/vnd.nice.syndication.guidance+json;version=1.0"}
        for count, guidance_id in enumerate(self.guidance_ids, start=1):
            try:
                response = await self.get(f"{API}/{guidance_id}", headers=headers)
            except Exception as exc:  # noqa: BLE001
                self.log.warning("nice_fetch_failed", guidance=guidance_id, error=str(exc))
                continue
            payload = response.json()
            sections: list[tuple[str, str]] = []
            for chapter in payload.get("chapters", []):
                for heading, body in html_to_sections(chapter.get("content", "")):
                    sections.append((f"{chapter.get('title', '').upper()} / {heading}", body))
            if not sections:
                continue
            last_modified = (payload.get("lastModified") or "")[:10]
            yield SourceDocument(
                doc_id=f"nice:{guidance_id.lower()}",
                source="nice",
                source_type=SourceType.UK_GUIDELINE,
                title=f"NICE {guidance_id}: {payload.get('title', '')}",
                text="\n\n".join(f"{h}: {b}" for h, b in sections),
                url=f"https://www.nice.org.uk/guidance/{guidance_id.lower()}",
                publisher="National Institute for Health and Care Excellence",
                updated=date.fromisoformat(last_modified) if last_modified else None,
                published=date.fromisoformat(last_modified) if last_modified else None,
                licence=Licence.SYNDICATION_LICENSED,
                jurisdiction="UK",
                sections=sections,
            )
            if limit and count >= limit:
                return
