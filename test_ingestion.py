from backend.app.domain import EvidenceLevel, Licence, SourceType
from ingestion.processing.chunker import chunk_document, split_sentences
from ingestion.processing.dedup import Deduplicator
from ingestion.seed import seed_documents
from ingestion.sources.europepmc import _licence
from ingestion.sources.openfda import parse_label
from ingestion.sources.pubmed import classify_publication_types, parse_pubmed_xml

PUBMED_XML = b"""<?xml version="1.0"?>
<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>12345678</PMID><Article>
<Journal><Title>Cochrane Database Syst Rev</Title><JournalIssue><PubDate><Year>2019</Year><Month>Apr</Month></PubDate></JournalIssue></Journal>
<ArticleTitle>Home use of interdental cleaning devices.</ArticleTitle>
<Abstract><AbstractText Label="BACKGROUND">Periodontal diseases are common.</AbstractText>
<AbstractText Label="AUTHORS' CONCLUSIONS">Flossing in addition to toothbrushing may reduce gingivitis.</AbstractText></Abstract>
<AuthorList><Author><LastName>Worthington</LastName><Initials>HV</Initials></Author></AuthorList>
<PublicationTypeList><PublicationType>Systematic Review</PublicationType></PublicationTypeList>
</Article><MeshHeadingList><MeshHeading><DescriptorName>Dental Devices, Home Care</DescriptorName></MeshHeading></MeshHeadingList>
</MedlineCitation><PubmedData><ArticleIdList><ArticleId IdType="doi">10.1002/14651858.CD012018.pub2</ArticleId></ArticleIdList></PubmedData>
</PubmedArticle></PubmedArticleSet>"""


def test_pubmed_parser_extracts_structure():
    [doc] = parse_pubmed_xml(PUBMED_XML)
    assert doc.doc_id == "pubmed:12345678"
    assert doc.source_type is SourceType.SYSTEMATIC_REVIEW
    assert [h for h, _ in doc.sections] == ["BACKGROUND", "AUTHORS' CONCLUSIONS"]
    assert doc.published.year == 2019 and doc.published.month == 4
    assert doc.doi.startswith("10.1002")


def test_publication_type_classification():
    assert classify_publication_types(["Randomized Controlled Trial"]) is SourceType.RANDOMISED_TRIAL
    assert classify_publication_types(["Journal Article"]) is SourceType.OTHER


def test_licence_parsing():
    assert _licence("cc by") is Licence.CC_BY
    assert _licence("cc by-nc") is Licence.CC_BY_NC


def test_openfda_label_parse():
    doc = parse_label({"set_id": "abc", "contraindications": ["Hypersensitivity."],
                       "drug_interactions": ["Warfarin."], "openfda": {"brand_name": ["Flagyl"]}}, "metronidazole")
    assert doc.jurisdiction == "US" and len(doc.sections) == 2


def test_sentence_splitter_respects_decimals_and_abbreviations():
    sentences = split_sentences("Use 0.5 mL e.g. in adults. Repeat after 5 minutes.")
    assert len(sentences) == 2


def test_chunks_never_cross_sections_and_carry_evidence():
    doc = seed_documents()[0]
    chunks = chunk_document(doc)
    assert {c.section for c in chunks} <= {h for h, _ in doc.sections}
    assert all(c.evidence_level is EvidenceLevel.NATIONAL_GUIDANCE for c in chunks)


def test_dedup_drops_near_duplicates():
    doc = seed_documents()[0]
    dup = doc.model_copy(update={"doc_id": "copy", "title": doc.title + "."})
    dedup = Deduplicator()
    assert dedup.add(doc) is doc
    assert dedup.add(dup) is None and dedup.dropped == 1
