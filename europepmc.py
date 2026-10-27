"""Europe PMC connector for open access full text articles.

Only records whose licence permits text mining and redistribution of derived
indexes (CC BY, CC0) are retained. Full text JATS XML is reduced to titled
sections so the chunker can respect document structure.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date

from lxml import etree

from backend.app.domain import Licence, SourceDocument
from ingestion.sources.base import SourceConnector
from ingestion.sources.pubmed import classify_publication_types

API = "https://www.ebi.ac.uk/europepmc/webservices/rest"
_SKIP_SECTIONS = {"references", "acknowledgements", "acknowledgments", "funding", "conflict of interest",
                  "competing interests", "author contributions", "supplementary material"}


def _licence(raw: str | None) -> Licence:
    value = (raw or "").lower().replace(" ", "")
    if value in {"cc0", "cc-zero"}:
        return Licence.CC0
    if value.startswith("ccby") and "nc" not in value:
        return Licence.CC_BY
    if value.startswith("ccby"):
        return Licence.CC_BY_NC
    return Licence.UNKNOWN


def parse_jats_sections(xml_bytes: bytes) -> list[tuple[str, str]]:
    root = etree.fromstring(xml_bytes)
    sections: list[tuple[str, str]] = []
    abstract = root.find(".//abstract")
    if abstract is not None:
        sections.append(("ABSTRACT", " ".join(abstract.itertext()).strip()))
    for sec in root.iterfind(".//body//sec"):
        if sec.getparent() is not None and sec.getparent().tag == "sec":
            continue  # nested sections are captured by their parent
        heading = (sec.findtext("title") or "SECTION").strip()
        if heading.lower() in _SKIP_SECTIONS:
            continue
        paragraphs = [" ".join(p.itertext()).strip() for p in sec.iter("p")]
        body = "\n".join(p for p in paragraphs if p)
        if body:
            sections.append((heading.upper(), body))
    return sections


class EuropePMCConnector(SourceConnector):
    name = "europepmc"
    requests_per_second = 5.0

    def __init__(self, query: str, include_full_text: bool = True, **options: object) -> None:
        super().__init__(**options)
        self.query = query
        self.include_full_text = include_full_text

    async def fetch(self, limit: int | None = None) -> AsyncIterator[SourceDocument]:
        cursor, yielded = "*", 0
        while True:
            response = await self.get(f"{API}/search", params={
                "query": self.query, "format": "json", "resultType": "core",
                "pageSize": 100, "cursorMark": cursor,
            })
            payload = response.json()
            results = payload.get("resultList", {}).get("result", [])
            if not results:
                return
            for record in results:
                licence = _licence(record.get("license"))
                if licence not in {Licence.CC_BY, Licence.CC0}:
                    continue
                pmcid = record.get("pmcid")
                sections: list[tuple[str, str]] = []
                if self.include_full_text and pmcid:
                    try:
                        xml = await self.get(f"{API}/{pmcid}/fullTextXML")
                        sections = parse_jats_sections(xml.content)
                    except Exception as exc:  # noqa: BLE001 - one bad record must not stop the run
                        self.log.warning("europepmc_fulltext_failed", pmcid=pmcid, error=str(exc))
                if not sections and record.get("abstractText"):
                    sections = [("ABSTRACT", record["abstractText"])]
                if not sections:
                    continue
                pub_types = record.get("pubTypeList", {}).get("pubType", [])
                year = record.get("pubYear")
                yield SourceDocument(
                    doc_id=f"pmc:{pmcid}" if pmcid else f"europepmc:{record.get('id')}",
                    source="europepmc",
                    source_type=classify_publication_types(pub_types),
                    title=record.get("title", "").rstrip("."),
                    text="\n\n".join(f"{h}: {b}" for h, b in sections),
                    url=f"https://europepmc.org/article/PMC/{pmcid}" if pmcid
                    else f"https://europepmc.org/abstract/MED/{record.get('pmid')}",
                    journal=record.get("journalInfo", {}).get("journal", {}).get("title"),
                    published=date(int(year), 1, 1) if year and year.isdigit() else None,
                    publication_types=pub_types,
                    doi=record.get("doi"),
                    licence=licence,
                    sections=sections,
                )
                yielded += 1
                if limit and yielded >= limit:
                    return
            next_cursor = payload.get("nextCursorMark")
            if not next_cursor or next_cursor == cursor:
                return
            cursor = next_cursor
