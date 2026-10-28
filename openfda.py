"""openFDA drug label connector.

US Structured Product Labels are public domain and give rich, consistent
sections on contraindications, interactions and adverse reactions. Because the
target jurisdiction is the UK, these documents are tagged jurisdiction=US and
the generator is instructed to prefer UK guidance (SDCEP, BNF derived) for
doses, using labels only for pharmacology and interaction context.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import date
from typing import Any

from backend.app.domain import Licence, SourceDocument, SourceType
from ingestion.sources.base import SourceConnector

API = "https://api.fda.gov/drug/label.json"

LABEL_SECTIONS = [
    ("indications_and_usage", "INDICATIONS AND USAGE"),
    ("contraindications", "CONTRAINDICATIONS"),
    ("boxed_warning", "BOXED WARNING"),
    ("warnings_and_cautions", "WARNINGS AND PRECAUTIONS"),
    ("warnings", "WARNINGS"),
    ("drug_interactions", "DRUG INTERACTIONS"),
    ("adverse_reactions", "ADVERSE REACTIONS"),
    ("use_in_specific_populations", "USE IN SPECIFIC POPULATIONS"),
    ("pregnancy", "PREGNANCY"),
    ("overdosage", "OVERDOSAGE"),
    ("mechanism_of_action", "MECHANISM OF ACTION"),
]


def parse_label(record: dict, generic: str) -> SourceDocument | None:
    sections = []
    for key, heading in LABEL_SECTIONS:
        values = record.get(key)
        if values:
            sections.append((heading, " ".join(values).strip()))
    if not sections:
        return None
    openfda = record.get("openfda", {})
    brand = (openfda.get("brand_name") or [generic.title()])[0]
    set_id = record.get("set_id", record.get("id"))
    effective = record.get("effective_time", "")
    published = None
    if len(effective) == 8 and effective.isdigit():
        published = date(int(effective[:4]), int(effective[4:6]), int(effective[6:]))
    return SourceDocument(
        doc_id=f"openfda:{set_id}",
        source="openfda",
        source_type=SourceType.DRUG_LABEL,
        title=f"{generic.title()} ({brand}) prescribing information",
        text="\n\n".join(f"{h}: {b}" for h, b in sections),
        url=f"https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid={set_id}",
        publisher="US Food and Drug Administration",
        published=published,
        licence=Licence.PUBLIC_DOMAIN_US_GOV,
        jurisdiction="US",
        sections=sections,
        extra={"generic_name": generic},
    )


class OpenFDALabelConnector(SourceConnector):
    name = "openfda"
    requests_per_second = 3.5

    def __init__(self, generic_names: list[str], per_drug: int = 3, **options: Any) -> None:
        super().__init__(**options)
        self.generic_names = generic_names
        self.per_drug = per_drug
        self.api_key = os.getenv("OPENFDA_API_KEY") or None

    async def fetch(self, limit: int | None = None) -> AsyncIterator[SourceDocument]:
        yielded = 0
        for generic in self.generic_names:
            params: dict[str, object] = {
                "search": f'openfda.generic_name:"{generic}"', "limit": self.per_drug,
            }
            if self.api_key:
                params["api_key"] = self.api_key
            try:
                response = await self.get(API, params=params)
            except Exception as exc:
                self.log.warning("openfda_lookup_failed", generic=generic, error=str(exc))
                continue
            for record in response.json().get("results", []):
                document = parse_label(record, generic)
                if document:
                    yield document
                    yielded += 1
                    if limit and yielded >= limit:
                        return
