import type { Retrieval, Source } from "../lib/api";

const LEVELS = [1, 2, 3, 4, 5, 6];

export function EvidenceTray({ sources, retrieval, latency, highlighted }: {
  sources: Source[];
  retrieval: Retrieval | null;
  latency: number | null;
  highlighted: number | null;
}) {
  return (
    <aside className="tray">
      <div className="panel">
        <div className="tray-head">
          <h2>Evidence</h2>
          <span className="note">{sources.length ? `${sources.length} passages` : "No sources yet"}</span>
        </div>
        <div className="sources">
          {!sources.length && (
            <p className="note" style={{ margin: 0 }}>
              Retrieved passages appear here with their evidence grade, so every citation can be checked against the original.
            </p>
          )}
          {sources.map((s) => {
            const cls = s.evidence_level === 6 ? "ev-6" : s.evidence_level >= 4 ? "ev-5" : "ev-low";
            return (
              <article key={s.id} id={`src-${s.id}`} className={`src${highlighted === s.id ? " flash" : ""}${s.superseded_by ? " superseded" : ""}`}>
                <div className="src-top">
                  <span className="src-n">{s.id}</span>
                  <div className="src-title"><a href={s.url} target="_blank" rel="noopener noreferrer">{s.title}</a></div>
                </div>
                <div className="src-meta">
                  <span className={`ev ${cls}`}>{s.evidence}</span>
                  {s.section && <span>{s.section}</span>}
                  {s.year && <span className="mono">{s.year}</span>}
                  {s.jurisdiction && <span className="mono">{s.jurisdiction}</span>}
                  <span className="mono">score {s.score.toFixed(2)}</span>
                </div>
                <div className="ladder" aria-label={`Evidence grade ${s.evidence_level} of 6`}>
                  {LEVELS.map((n) => <i key={n} className={n <= s.evidence_level ? "on" : ""} />)}
                </div>
                {s.superseded_by && (
                  <div className="superseded-note">
                    Superseded. Current guidance: <a href={s.superseded_by.url} target="_blank" rel="noopener noreferrer">{s.superseded_by.title}</a>
                  </div>
                )}
                <div className="src-snip">{s.snippet.length > 260 ? `${s.snippet.slice(0, 260)}…` : s.snippet}</div>
              </article>
            );
          })}
        </div>
      </div>
      <div className="panel">
        <div className="tray-head"><h2>Retrieval trace</h2></div>
        <div className="trace">
          <div><b>{retrieval?.candidates ?? 0}</b><span>candidates fused</span></div>
          <div><b>{retrieval ? Math.round(retrieval.dense_ms + retrieval.sparse_ms + retrieval.rerank_ms) : 0} ms</b><span>retrieval</span></div>
          <div><b>{latency ? Math.round(latency) : 0} ms</b><span>end to end</span></div>
          <div><b>{retrieval?.query_coverage != null ? `${Math.round(retrieval.query_coverage * 100)}%` : "n/a"}</b><span>question coverage</span></div>
          <div><b>{retrieval?.superseded ?? 0}</b><span>superseded demoted</span></div>
          <div><b>{retrieval?.returned ?? 0}</b><span>passages used</span></div>
        </div>
      </div>
    </aside>
  );
}
