import json

import pytest

from backend.app.config import Settings
from backend.app.retrieval.bm25 import BM25Index
from backend.app.retrieval.vector_store import InMemoryVectorStore, _matches
from ingestion import cli
from ingestion.pipeline import connector_kwargs, index_documents, iter_raw, load_corpus_config
from ingestion.seed import seed_documents
from ingestion.sources import REGISTRY


@pytest.fixture()
def offline_settings(tmp_path):
    return Settings(_env_file=None, env="test", data_dir=tmp_path, embedding_backend="hashing",
                    reranker_backend="none", vector_backend="memory", redis_url=None)


def test_registry_has_every_configured_source():
    config = load_corpus_config(cli.DEFAULT_CONFIG)
    assert set(REGISTRY) == {"nice", "sdcep", "govuk", "europepmc", "pubmed", "openfda", "medlineplus"}
    for source in REGISTRY:
        assert connector_kwargs(source, config), source


def test_pubmed_jobs_put_priority_types_first():
    jobs = connector_kwargs("pubmed", load_corpus_config(cli.DEFAULT_CONFIG))
    assert "Systematic Review[pt]" in jobs[0]["term"]
    assert all("humans[mh]" in job["term"] for job in jobs)


def test_index_documents_builds_both_indexes_and_manifest(offline_settings):
    docs = seed_documents()
    manifest = index_documents(offline_settings, [*docs, docs[0].model_copy(update={"doc_id": "dup"})])
    assert manifest["documents_indexed"] == len(docs) and manifest["duplicates_dropped"] == 1
    assert manifest["superseded_chunks"] == 0
    index_dir = offline_settings.index_dir
    store = InMemoryVectorStore.load(index_dir / "dense")
    bm25 = BM25Index.load(index_dir / "bm25.pkl")
    assert store.count() == manifest["chunks"] == len(bm25)
    assert json.loads((index_dir / "manifest.json").read_text())["licences"]


def test_iter_raw_reads_in_licence_priority_order(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    docs = seed_documents()
    (raw / "pubmed.jsonl").write_text(docs[1].model_dump_json() + "\n")
    (raw / "nice.jsonl").write_text(docs[0].model_dump_json() + "\n\n")
    ordered = list(iter_raw(raw, ["pubmed", "nice", "openfda"]))
    assert [d.doc_id for d in ordered] == [docs[0].doc_id, docs[1].doc_id]


def test_cli_seed_and_stats(offline_settings, monkeypatch, capsys):
    monkeypatch.setattr(cli, "get_settings", lambda: offline_settings)
    cli.main(["stats"])
    assert "No index built yet" in capsys.readouterr().out
    cli.main(["seed"])
    out = capsys.readouterr().out
    assert json.loads(out[out.index("{\n"):])["chunks"] > 0  # structured log lines precede the manifest
    cli.main(["stats"])
    assert '"documents_indexed"' in capsys.readouterr().out


def test_vector_store_filters_save_load_and_delete(tmp_path, seed_chunks):
    from backend.app.retrieval.embedder import HashingEmbedder

    embedder = HashingEmbedder(64)
    store = InMemoryVectorStore(64)
    store.upsert(seed_chunks, embedder.embed_documents([c.text for c in seed_chunks]))
    store.upsert(seed_chunks[:1], embedder.embed_documents([seed_chunks[0].text]))  # idempotent update
    assert store.count() == len(seed_chunks)
    store.save(tmp_path / "dense")
    loaded = InMemoryVectorStore.load(tmp_path / "dense")
    hits = loaded.search(embedder.embed_query("fluoride"), 5, {"source_type": ["uk_guideline"], "jurisdiction": "UK"})
    assert hits and all(_matches(c, {"min_evidence_level": 6}) for c, _ in hits)
    assert loaded.delete([seed_chunks[0].chunk_id, "missing"]) == 1
    assert loaded.count() == len(seed_chunks) - 1 and not loaded.get([seed_chunks[0].chunk_id])
