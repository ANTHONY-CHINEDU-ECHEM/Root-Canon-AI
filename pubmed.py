"""PubMed connector using the NCBI Entrez E-utilities.

Strategy
  1. ESearch with usehistory=y so very large result sets stay on the NCBI
     history server instead of being paged through in memory.
  2. EFetch in batches of 200 PMIDs as XML.
  3. Parse structured abstracts section by section so the chunker can keep
     BACKGROUND, METHODS, RESULTS and CONCLUSIONS apart.

NCBI allows 3 requests per second anonymously and 10 with an API key.
Abstracts are indexed under fair dealing for research; full text is only
indexed through Europe PMC when the licence permits.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import date

from lxml import etree

from backend.app.domain import Licence, SourceDocument, SourceType
from ingestion.sources.base import SourceConnector

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
BATCH = 200

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}

_PT_TO_SOURCE_TYPE = [
    ("practice guideline", SourceType.UK_GUIDELINE),
    ("guideline", SourceType.UK_GUIDELINE),
    ("systematic review", SourceType.SYSTEMATIC_REVIEW),
    ("meta-analysis", SourceType.SYSTEMATIC_REVIEW),
    ("randomized controlled trial", SourceType.RANDOMISED_TRIAL),
    ("controlled clinical trial", SourceType.RANDOMISED_TRIAL),
    ("observational study", SourceType.OBSERVATIONAL),
    ("comparative study", SourceType.OBSERVATIONAL),
    ("case reports", SourceType.CASE_REPORT),
    ("review", SourceType.NARRATIVE_REVIEW),
]


def classify_publication_types(pub_types: list[str]) -> SourceType:
    lowered = [p.lower() for p in pub_types]
    for needle, source_type in _PT_TO_SOURCE_TYPE:
        if any(needle in p for p in lowered):
            # PubMed "Practice Guideline" is usually not UK national guidance.
            if source_type is SourceType.UK_GUIDELINE:
                return SourceType.NARRATIVE_REVIEW
            return source_type
    return SourceType.OTHER


def _text(node: etree._Element | None) -> str:
    return "".join(node.itertext()).strip() if node is not None else ""


def _parse_date(article: etree._Element) -> date | None:
    pub_date = article.find(".//Journal/JournalIssue/PubDate")
    if pub_date is None:
        return None
    year = pub_date.findtext("Year")
    if not year:
        medline = pub_date.findtext("MedlineDate") or ""
        year = medline[:4]
    if not year or not year.isdigit():
        return None
    month_raw = (pub_date.findtext("Month") or "1").lower()[:3]
    month = _MONTHS.get(month_raw, int(month_raw) if month_raw.isdigit() else 1)
    day_raw = pub_date.findtext("Day") or "1"
    try:
        return date(int(year), max(1, min(month, 12)), max(1, min(int(day_raw), 28)))
    except ValueError:
        return date(int(year), 1, 1)


def parse_pubmed_xml(xml_bytes: bytes) -> list[SourceDocument]:
    """Parse an EFetch PubmedArticleSet into SourceDocuments."""
    root = etree.fromstring(xml_bytes)
    documents: list[SourceDocument] = []
    for article in root.iterfind(".//PubmedArticle"):
        pmid = article.findtext(".//MedlineCitation/PMID")
        title = _text(article.find(".//ArticleTitle"))
        abstract_nodes = article.findall(".//Abstract/AbstractText")
        if not pmid or not title or not abstract_nodes:
            continue
        sections: list[tuple[str, str]] = []
        for node in abstract_nodes:
            label = node.get("Label") or node.get("NlmCategory") or "ABSTRACT"
            body = _text(node)
            if body:
                sections.append((label.upper(), body))
        pub_types = [_text(p) for p in article.findall(".//PublicationTypeList/PublicationType")]
        mesh = [_text(m) for m in article.findall(".//MeshHeadingList/MeshHeading/DescriptorName")]
        authors = []
        for author in article.findall(".//AuthorList/Author"):
            last, initials = author.findtext("LastName"), author.findtext("Initials")
            if last:
                authors.append(f"{last} {initials or ''}".strip())
        doi = None
        for aid in article.findall(".//ArticleIdList/ArticleId"):
            if aid.get("IdType") == "doi":
                doi = _text(aid)
        documents.append(
            SourceDocument(
                doc_id=f"pubmed:{pmid}",
                source="pubmed",
                source_type=classify_publication_types(pub_types),
                title=title,
                text="\n\n".join(f"{h}: {b}" for h, b in sections),
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                journal=_text(article.find(".//Journal/Title")) or None,
                authors=authors[:12],
                published=_parse_date(article),
                publication_types=pub_types,
                mesh_terms=mesh,
                doi=doi,
                licence=Licence.ABSTRACT_FAIR_DEALING,
                sections=sections,
            )
        )
    return documents


class PubMedConnector(SourceConnector):
    name = "pubmed"

    def __init__(self, term: str, **options: object) -> None:
        self.api_key = os.getenv("NCBI_API_KEY") or None
        self.email = os.getenv("NCBI_EMAIL") or None
        self.requests_per_second = 9.0 if self.api_key else 2.8
        super().__init__(**options)
        self.term = term

    def _params(self, **extra: object) -> dict[str, object]:
        params: dict[str, object] = {"db": "pubmed", "tool": "root_canon_ai", **extra}
        if self.api_key:
            params["api_key"] = self.api_key
        if self.email:
            params["email"] = self.email
        return params

    async def search(self) -> tuple[int, str, str]:
        response = await self.get(
            f"{EUTILS}/esearch.fcgi",
            params=self._params(term=self.term, usehistory="y", retmode="json", retmax=0),
        )
        result = response.json()["esearchresult"]
        return int(result["count"]), result["webenv"], result["querykey"]

    async def fetch(self, limit: int | None = None) -> AsyncIterator[SourceDocument]:
        count, webenv, query_key = await self.search()
        total = min(count, limit) if limit else count
        self.log.info("pubmed_search", term=self.term, count=count, fetching=total)
        for start in range(0, total, BATCH):
            response = await self.get(
                f"{EUTILS}/efetch.fcgi",
                params=self._params(
                    WebEnv=webenv, query_key=query_key, retstart=start,
                    retmax=min(BATCH, total - start), retmode="xml",
                ),
            )
            for document in parse_pubmed_xml(response.content):
                yield document
