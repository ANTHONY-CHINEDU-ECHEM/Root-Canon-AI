"""MedlinePlus health topics via the NLM web service.

Used for plain language patient information, which helps the assistant draft
patient facing explanations. Content is produced by the US National Library of
Medicine and is in the public domain.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from typing import Any

from lxml import etree

from backend.app.domain import Licence, SourceDocument, SourceType
from ingestion.sources.base import SourceConnector

API = "https://wsearch.nlm.nih.gov/ws/query"
_TAGS = re.compile(r"<[^>]+>")


def parse_health_topics(xml_bytes: bytes) -> list[SourceDocument]:
    root = etree.fromstring(xml_bytes)
    documents = []
    for doc in root.iterfind(".//document"):
        url = doc.get("url", "")
        fields = {c.get("name"): "".join(c.itertext()) for c in doc.findall("content")}
        title = _TAGS.sub("", fields.get("title", "")).strip()
        summary = _TAGS.sub(" ", fields.get("FullSummary", "")).strip()
        if not title or not summary:
            continue
        documents.append(SourceDocument(
            doc_id=f"medlineplus:{url.rstrip('/').rsplit('/', 1)[-1]}",
            source="medlineplus",
            source_type=SourceType.PATIENT_INFORMATION,
            title=title,
            text=re.sub(r"\s+", " ", summary),
            url=url,
            publisher="US National Library of Medicine",
            licence=Licence.PUBLIC_DOMAIN_US_GOV,
            jurisdiction="US",
            sections=[("SUMMARY", re.sub(r"\s+", " ", summary))],
        ))
    return documents


class MedlinePlusConnector(SourceConnector):
    name = "medlineplus"
    requests_per_second = 1.5  # NLM asks for no more than 85 requests per minute

    def __init__(self, topics: list[str], **options: Any) -> None:
        super().__init__(**options)
        self.topics = topics

    async def fetch(self, limit: int | None = None) -> AsyncIterator[SourceDocument]:
        seen: set[str] = set()
        for topic in self.topics:
            response = await self.get(API, params={"db": "healthTopics", "term": topic, "retmax": 20})
            for document in parse_health_topics(response.content):
                if document.doc_id in seen:
                    continue
                seen.add(document.doc_id)
                yield document
                if limit and len(seen) >= limit:
                    return
