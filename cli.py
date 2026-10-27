"""Command line entry point for ingestion.

Examples
    python -m ingestion.cli ingest --sources all
    python -m ingestion.cli ingest --sources pubmed europepmc --limit 5000
    python -m ingestion.cli ingest --from-raw            # rebuild the index only
    python -m ingestion.cli stats
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.app.config import get_settings
from backend.app.logging_setup import configure_logging
from ingestion.pipeline import SOURCE_ORDER, run

DEFAULT_CONFIG = Path(__file__).parent / "config" / "dental_corpus.yaml"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="root-canon-ingest", description="Build the Root Canon AI knowledge base.")
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="Harvest sources and build the indexes")
    ingest.add_argument("--sources", nargs="+", default=["all"], choices=["all", *SOURCE_ORDER])
    ingest.add_argument("--limit", type=int, default=None, help="Max documents per query job")
    ingest.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    ingest.add_argument("--from-raw", action="store_true", help="Skip harvesting, rebuild from data/raw")

    sub.add_parser("seed", help="Index the bundled UK guidance seed set (offline, seconds)")
    sub.add_parser("stats", help="Print the current index manifest")

    args = parser.parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level)

    if args.command == "ingest":
        sources = SOURCE_ORDER if "all" in args.sources else args.sources
        manifest = run(settings, args.config, sources, args.limit, from_raw=args.from_raw)
        print(json.dumps(manifest, indent=2))
    elif args.command == "seed":
        from ingestion.pipeline import index_documents
        from ingestion.seed import seed_documents

        print(json.dumps(index_documents(settings, seed_documents()), indent=2))
    elif args.command == "stats":
        path = settings.index_dir / "manifest.json"
        print(path.read_text() if path.exists() else "No index built yet. Run: make ingest")


if __name__ == "__main__":
    main()
