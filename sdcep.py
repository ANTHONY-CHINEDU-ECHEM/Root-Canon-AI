"""SDCEP guidance connector.

The Scottish Dental Clinical Effectiveness Programme publishes the prescribing
guidance most UK dentists use chairside. Pages are fetched one at a time,
robots.txt is honoured, navigation chrome is stripped and only the guidance
body is retained. Operators must review the SDCEP terms before redistributing
an index built from these pages.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from lxml import html as lxml_html

from backend.app.domain import Licence, SourceDocument, SourceType
from ingestion.sources.base import SourceConnector

_CONTENT_XPATHS = ["//main", "//article", "//*[@id='content']", "//body"]
_STRIP = ["//nav", "//header", "//footer", "//script", "//style", "//form", "//*[contains(@class,'breadcrumb')]"]


def extract_guidance(page_html: str) -> tuple[str, list[tuple[str, str]]]:
    tree = lxml_html.fromstring(page_html)
    for xpath in _STRIP:
        for node in tree.xpath(xpath):
            node.drop_tree()
    container = next((found[0] for xp in _CONTENT_XPATHS if (found := tree.xpath(xp))), tree)
    title_nodes = container.xpath(".//h1")
    title = " ".join(title_nodes[0].text_content().split()) if title_nodes else "SDCEP guidance"
    sections: list[tuple[str, str]] = []
    heading, buffer = "GUIDANCE", list[str]()
    for element in container.iter():
        if element.tag in {"h2", "h3"}:
            if buffer:
                sections.append((heading, "\n".join(buffer)))
            heading, buffer = " ".join(element.text_content().split()).upper(), []
        elif element.tag in {"p", "li"}:
            text = " ".join(element.text_content().split())
            if text:
                buffer.append(text)
    if buffer:
        sections.append((heading, "\n".join(buffer)))
    return title, sections


class SDCEPConnector(SourceConnector):
    name = "sdcep"
    requests_per_second = 0.5
    respect_robots = True

    def __init__(self, urls: list[str], **options: Any) -> None:
        super().__init__(**options)
        self.urls = urls

    async def fetch(self, limit: int | None = None) -> AsyncIterator[SourceDocument]:
        for count, url in enumerate(self.urls, start=1):
            try:
                response = await self.get(url)
            except Exception as exc:
                self.log.warning("sdcep_fetch_failed", url=url, error=str(exc))
                continue
            title, sections = extract_guidance(response.text)
            if not sections:
                continue
            slug = url.rstrip("/").rsplit("/", 1)[-1]
            yield SourceDocument(
                doc_id=f"sdcep:{slug}",
                source="sdcep",
                source_type=SourceType.UK_GUIDELINE,
                title=f"SDCEP: {title}",
                text="\n\n".join(f"{h}: {b}" for h, b in sections),
                url=url,
                publisher="Scottish Dental Clinical Effectiveness Programme",
                licence=Licence.UNKNOWN,
                jurisdiction="UK",
                sections=sections,
            )
            if limit and count >= limit:
                return
