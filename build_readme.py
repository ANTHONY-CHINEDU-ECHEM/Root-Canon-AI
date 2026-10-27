"""Assemble README.md from docs/README.template.md and docs/architecture.mmd.

Keeping the Mermaid source in one file means the README diagram and the
standalone diagram can never drift apart. The README is checked in CI for
hyphens and dashes, so this script refuses to write one that contains any.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    template = (ROOT / "docs" / "README.template.md").read_text(encoding="utf-8")
    mermaid = (ROOT / "docs" / "architecture.mmd").read_text(encoding="utf-8").strip()
    readme = template.replace("__MERMAID__", mermaid)
    bad = [(i + 1, line) for i, line in enumerate(readme.splitlines()) if re.search("[\u2014\u2013-]", line)]
    if bad:
        raise SystemExit("README would contain hyphens or dashes:\n" + "\n".join(f"{n}: {text}" for n, text in bad))
    (ROOT / "README.md").write_text(readme + "\n", encoding="utf-8")
    print("README.md written")


if __name__ == "__main__":
    main()
