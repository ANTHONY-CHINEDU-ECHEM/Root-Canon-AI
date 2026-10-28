"""GOV.UK Content API connector.

Delivering Better Oral Health (Office for Health Improvement and Disparities)
is the evidence based prevention toolkit used across English dental practice.
It is published under the Open Government Licence v3.0, which permits reuse.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date
from typing import Any

from lxml import html as lxml_html

from backend.app.domain import Licence, SourceDocument, SourceType
from ingestion.sources.base import SourceConnector

API = "https://www.gov.uk/api/content"


def html_to_sections(body_html: str) -> list[tuple[str, str]]:
    """Split GOV.UK body HTML into (heading, text) sections on h2 and h3."""
    tree = lxml_html.fromstring(f"<div>{body_html}</div>")
    sections: list[tuple[str, str]] = []
    heading, buffer = "INTRODUCTION", list[str]()
    for element in tree.iter():
        if element.tag in {"h2", "h3"}:
            if buffer:
                sections.append((heading, "\n".join(buffer)))
            heading, buffer = element.text_content().strip().upper(), []
        elif element.tag in {"p", "li", "td", "th"}:
            text = " ".join(element.text_content().split())
            if text and element.getparent() is not None and element.getparent().tag not in {"li"}:
                buffer.append(f"* {text}" if element.tag == "li" else text)
    if buffer:
        sections.append((heading, "\n".join(buffer)))
    return sections


class GovUKContentConnector(SourceConnector):
    name = "govuk"
    requests_per_second = 2.0

    def __init__(self, base_paths: list[str], **options: Any) -> None:
        super().__init__(**options)
        self.base_paths = base_paths

    async def fetch(self, limit: int | None = None) -> AsyncIterator[SourceDocument]:
        for count, path in enumerate(self.base_paths, start=1):
            response = await self.get(f"{API}{path}")
            payload = response.json()
            body = payload.get("details", {}).get("body", "")
            sections = html_to_sections(body)
            if not sections:
                continue
            updated = payload.get("public_updated_at", "")[:10]
            yield SourceDocument(
                doc_id=f"govuk:{path.rsplit('/', 1)[-1]}",
                source="govuk",
                source_type=SourceType.UK_GUIDELINE,
                title=f"Delivering better oral health: {payload.get('title', '').strip()}",
                text="\n\n".join(f"{h}: {b}" for h, b in sections),
                url=f"https://www.gov.uk{path}",
                publisher="Office for Health Improvement and Disparities",
                updated=date.fromisoformat(updated) if updated else None,
                published=date.fromisoformat(updated) if updated else None,
                licence=Licence.OPEN_GOVERNMENT,
                jurisdiction="UK",
                sections=sections,
            )
            if limit and count >= limit:
                return
