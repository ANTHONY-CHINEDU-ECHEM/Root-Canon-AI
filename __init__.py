"""Source connectors, keyed by the name used in the corpus config and CLI."""

from __future__ import annotations

from ingestion.sources.base import SourceConnector
from ingestion.sources.europepmc import EuropePMCConnector
from ingestion.sources.govuk import GovUKContentConnector
from ingestion.sources.medlineplus import MedlinePlusConnector
from ingestion.sources.nice import NICESyndicationConnector
from ingestion.sources.openfda import OpenFDALabelConnector
from ingestion.sources.pubmed import PubMedConnector
from ingestion.sources.sdcep import SDCEPConnector

REGISTRY: dict[str, type[SourceConnector]] = {
    connector.name: connector
    for connector in (
        NICESyndicationConnector,
        SDCEPConnector,
        GovUKContentConnector,
        EuropePMCConnector,
        PubMedConnector,
        OpenFDALabelConnector,
        MedlinePlusConnector,
    )
}

__all__ = ["REGISTRY", "SourceConnector"]
