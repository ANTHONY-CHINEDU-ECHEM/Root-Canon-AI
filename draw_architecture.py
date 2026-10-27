"""Generate docs/architecture.svg, the vector system architecture diagram.

The diagram is produced from code so it stays in sync with the system and
renders crisply at any zoom on GitHub.

    python -m scripts.draw_architecture
"""

from __future__ import annotations

from html import escape
from pathlib import Path

W, H = 1480, 1010
INK, MUTED, LINE, PAPER = "#15242a", "#5a6a6f", "#c9d3cf", "#ffffff"
ROSE, ROSE_SOFT, GREEN, GREEN_SOFT, AMBER, AMBER_SOFT, SLATE_SOFT = (
    "#a83a4f", "#f8e9ec", "#2c6a57", "#e3f1ea", "#8a5a00", "#fbf0d9", "#eef2f1")

parts: list[str] = []


def text(x, y, s, size=12, weight=400, fill=INK, anchor="start", italic=False):  # type: ignore[no-untyped-def]
    style = ' font-style="italic"' if italic else ""
    parts.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{fill}" '
                 f'text-anchor="{anchor}"{style}>{escape(s)}</text>')


def box(x, y, w, h, title, lines=(), fill=PAPER, stroke=INK, title_fill=INK, step=None):  # type: ignore[no-untyped-def]
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill}" stroke="{stroke}" stroke-width="1.4"/>')
    tx = x + 14
    if step:
        parts.append(f'<circle cx="{x + 22}" cy="{y + 22}" r="11" fill="{stroke}"/>')
        text(x + 22, y + 26.5, step, 11.5, 700, PAPER, "middle")
        tx = x + 40
    text(tx, y + 27, title, 14.5, 700, title_fill)
    for i, line in enumerate(lines):
        text(x + 14, y + 50 + i * 17, line, 12, 400, MUTED)


def arrow(points, color=INK, dashed=False, label=None, label_at=None, width=1.6):  # type: ignore[no-untyped-def]
    d = "M " + " L ".join(f"{px} {py}" for px, py in points)
    dash = ' stroke-dasharray="6 5"' if dashed else ""
    marker = "ah-ink" if color == INK else ("ah-rose" if color == ROSE else "ah-green")
    parts.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}"{dash} marker-end="url(#{marker})"/>')
    if label and label_at:
        lx, ly = label_at
        width_est = len(label) * 6.4 + 14
        parts.append(f'<rect x="{lx - width_est / 2}" y="{ly - 13}" width="{width_est}" height="19" rx="9.5" fill="{PAPER}" stroke="{LINE}"/>')
        text(lx, ly + 1, label, 11, 600, color if color != INK else MUTED, "middle")


def band(y, h, label, sub, fill):  # type: ignore[no-untyped-def]
    parts.append(f'<rect x="20" y="{y}" width="{W - 40}" height="{h}" rx="14" fill="{fill}" stroke="{LINE}"/>')
    text(40, y + 28, label.upper(), 12, 700, INK)
    text(40, y + 46, sub, 11.5, 400, MUTED)


# Canvas and title
parts.append(f'<rect width="{W}" height="{H}" fill="{PAPER}"/>')
text(40, 44, "Root Canon AI", 26, 700, INK)
text(232, 44, "System architecture", 26, 400, ROSE)
text(40, 68, "Evidence grounded clinical decision support for UK dental surgery. Retrieval augmented generation over real, licensed sources.", 13, 400, MUTED)

# Band A: ingestion
band(90, 330, "A  Knowledge ingestion", "Offline, resumable, licence aware. Streams hundreds of thousands of records.", SLATE_SOFT)
sources = [("NICE syndication API", "UK guidance"), ("SDCEP guidance", "UK prescribing"), ("GOV.UK content API", "DBOH toolkit"),
           ("Europe PMC", "open access"), ("PubMed E-utilities", "MeSH families"),
           ("openFDA labels", "37 dental medicines"), ("MedlinePlus", "patient information")]
for i, (name, sub) in enumerate(sources):
    y = 150 + i * 37
    uk = i < 3
    parts.append(f'<rect x="40" y="{y}" width="228" height="30" rx="7" fill="{GREEN_SOFT if uk else PAPER}" stroke="{GREEN if uk else LINE}"/>')
    text(52, y + 19.5, name, 12, 700, GREEN if uk else INK)
    text(256, y + 19.5, sub, 10.5, 400, MUTED, "end")
    arrow([(268, y + 15), (298, y + 15), (298, 265), (316, 265)], INK, width=1.1)

box(320, 200, 200, 130, "Harvest", ["Rate limited per source", "Retries with backoff", "robots.txt honoured", "Raw JSONL checkpoint"], step="1")
box(548, 200, 200, 130, "Normalise", ["Encoding and unit safe", "cleaning (1:80,000 kept)", "SimHash near duplicate", "removal, licence ranked"], step="2")
box(776, 200, 200, 130, "Chunk and grade", ["Section aware, 320 tokens", "Sentence overlap", "Evidence grade 0 to 6", "Recency and jurisdiction"], step="3")
box(1004, 200, 170, 130, "Embed", ["BGE base, 768 dims", "Title and section", "context header", "Batches of 256"], step="4")
for x1, x2 in ((520, 548), (748, 776), (976, 1004)):
    arrow([(x1, 265), (x2 - 2, 265)])
arrow([(1174, 265), (1206, 265)])

parts.append(f'<rect x="1210" y="140" width="230" height="260" rx="10" fill="{PAPER}" stroke="{ROSE}" stroke-width="1.4"/>')
text(1226, 167, "Index stores", 14.5, 700, ROSE)
for i, (name, sub) in enumerate([("Qdrant", "HNSW, cosine, payload filters"), ("BM25 index", "clinical tokenizer"),
                                  ("Raw corpus", "JSONL per source"), ("Manifest", "counts, licences, timings")]):
    y = 182 + i * 53
    parts.append(f'<rect x="1226" y="{y}" width="198" height="44" rx="7" fill="{ROSE_SOFT}" stroke="none"/>')
    text(1238, y + 19, name, 12.5, 700, INK)
    text(1238, y + 35, sub, 11, 400, MUTED)

# Band B: query path
band(440, 400, "B  Question answering", "Online and streamed.", PAPER)
by, bh = 560, 150
box(40, by, 190, bh, "Clinician interface", ["React and TypeScript", "Streaming answers", "Evidence tray with", "grade and citations"], fill=PAPER)
box(258, by, 190, bh, "API gateway", ["FastAPI, X-API-Key", "Per key rate limit", "Request correlation", "Redis answer cache"], step="1")
box(476, by, 200, bh, "Guardrails", ["PII redaction (NHS no.", "mod 11, postcode, DOB)", "Emergency triage first", "Dental scope check"], fill=AMBER_SOFT, stroke=AMBER, title_fill=AMBER, step="2")
box(704, by, 228, bh, "Hybrid retriever", ["Dense top 40 and BM25 top 40", "Reciprocal rank fusion", "Cross encoder rerank", "Evidence, recency, UK prior"], step="3")
box(960, by, 210, bh, "LLM router", ["Claude (default)", "OpenAI (switchable)", "Ollama (on premises)", "Cached system prompt"], fill=ROSE_SOFT, stroke=ROSE, title_fill=ROSE, step="4")
box(1198, by, 242, bh, "Citation validator", ["Invalid ids removed", "Sentence citation coverage", "Every dose matched to a", "cited source, else flagged"], fill=GREEN_SOFT, stroke=GREEN, title_fill=GREEN, step="5")

mid = by + 62
arrow([(230, mid), (256, mid)])
arrow([(448, mid), (474, mid)])
arrow([(676, mid), (702, mid)])
arrow([(932, mid), (958, mid)])
arrow([(1170, mid), (1196, mid)])

# Retrieval reads the indexes
arrow([(1325, 400), (1325, 488), (818, 488), (818, by - 2)], ROSE, dashed=True, label="vector and lexical lookup", label_at=(1060, 492))
# Emergency short circuit
parts.append(f'<path d="M 576 {by + bh} L 576 742 L 150 742 L 150 {by + bh + 4}" fill="none" stroke="{AMBER}" stroke-width="1.6" marker-end="url(#ah-amber)"/>')
parts.append(f'<rect x="282" y="730" width="190" height="19" rx="9.5" fill="{PAPER}" stroke="{LINE}"/>')
text(377, 743.5, "emergency banner sent first", 11, 600, AMBER, "middle")
# Response stream back to the UI
parts.append(f'<path d="M 1319 {by + bh} L 1319 790 L 110 790 L 110 {by + bh + 4}" fill="none" stroke="{GREEN}" stroke-width="1.8" marker-end="url(#ah-green)"/>')
parts.append(f'<rect x="560" y="778" width="380" height="20" rx="10" fill="{PAPER}" stroke="{LINE}"/>')
text(750, 792, "SSE stream: meta, emergency, sources, tokens, final", 11, 600, GREEN, "middle")
# Evidence gate annotation
parts.append(f'<rect x="704" y="{by + bh + 14}" width="228" height="40" rx="8" fill="{SLATE_SOFT}" stroke="{LINE}"/>')
text(716, by + bh + 31, "Injection filter and evidence gate", 11.5, 700, INK)
text(716, by + bh + 47, "Abstain when best evidence is weak", 11, 400, MUTED)
# Deterministic tools
parts.append(f'<rect x="300" y="478" width="480" height="56" rx="10" fill="{PAPER}" stroke="{GREEN}" stroke-dasharray="5 4"/>')
text(314, 500, "Deterministic clinical tools: numbers never come from the model", 13.5, 700, GREEN)
text(314, 520, "SDCEP regimens, LA maximum dose, adrenaline by age, interactions", 11.5, 400, MUTED)
arrow([(353, by), (353, 536)], GREEN)

# Band C: operations
band(850, 140, "C  Operations and assurance", "Observable and gated.", SLATE_SOFT)
ops = [("Audit log", "hashed question, sources,", "coverage, provider"),
       ("Prometheus metrics", "latency, outcomes, coverage,", "unsupported figures"),
       ("Evaluation gate", "golden UK questions: hit@5,", "MRR, abstention, triage"),
       ("Container stack", "API, Qdrant, Redis, frontend,", "Ollama and Prometheus profiles"),
       ("CI pipeline", "ruff, pytest, eval gate,", "README style gate, build")]
for i, (name, a, b) in enumerate(ops):
    x = 300 + i * 228
    parts.append(f'<rect x="{x}" y="876" width="212" height="96" rx="10" fill="{PAPER}" stroke="{LINE}"/>')
    text(x + 14, 902, name, 13.5, 700, INK)
    text(x + 14, 924, a, 11.5, 400, MUTED)
    text(x + 14, 941, b, 11.5, 400, MUTED)

defs = f"""<defs>
<marker id="ah-ink" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="{INK}"/></marker>
<marker id="ah-rose" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="{ROSE}"/></marker>
<marker id="ah-green" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="{GREEN}"/></marker>
<marker id="ah-amber" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="{AMBER}"/></marker>
</defs>"""

svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
       f'font-family="Segoe UI, Helvetica Neue, Arial, sans-serif" role="img" aria-label="Root Canon AI system architecture">'
       f"<title>Root Canon AI system architecture</title>{defs}{''.join(parts)}</svg>\n")

out = Path(__file__).resolve().parents[1] / "docs" / "architecture.svg"
out.write_text(svg, encoding="utf-8")
print(f"wrote {out}")
