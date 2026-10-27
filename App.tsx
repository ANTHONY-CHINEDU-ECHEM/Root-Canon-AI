import { useEffect, useState } from "react";
import { Consult } from "./components/Consult";
import { Tools } from "./components/Tools";
import { health } from "./lib/api";

type View = "assistant" | "tools";

function Mark() {
  return (
    <svg width="34" height="34" viewBox="0 0 34 34" aria-hidden="true">
      <rect x="0.5" y="0.5" width="33" height="33" rx="8" fill="var(--accent-soft)" stroke="var(--accent)" />
      <path d="M10 9c2.2-1.6 4.4-.9 7 0 2.6-.9 4.8-1.6 7 0 1.6 1.3 1.6 4.2.7 7-.8 2.5-1.2 4.6-1.6 7.4-.3 2.1-2.4 2.3-2.9.3-.5-2-1-4.3-3.2-4.3s-2.7 2.3-3.2 4.3c-.5 2-2.6 1.8-2.9-.3-.4-2.8-.8-4.9-1.6-7.4-.9-2.8-.9-5.7.7-7Z" fill="none" stroke="var(--accent)" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M14.5 13.5h5M17 11v5" stroke="var(--guide)" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

export function App() {
  const [view, setView] = useState<View>("assistant");
  const [status, setStatus] = useState("Connecting");

  useEffect(() => {
    health().then((h) => setStatus(`${h.chunks_indexed.toLocaleString("en-GB")} passages indexed`))
      .catch(() => setStatus("API unreachable"));
  }, []);

  return (
    <>
      <header className="top">
        <div className="top-inner">
          <div className="brand">
            <Mark />
            <div>
              <div className="brand-name">Root Canon <em>AI</em></div>
              <div className="brand-sub">UK dental decision support</div>
            </div>
          </div>
          <nav className="tabs" role="tablist" aria-label="Sections">
            {(["assistant", "tools"] as const).map((v) => (
              <button key={v} role="tab" aria-selected={view === v} onClick={() => setView(v)}>
                {v === "assistant" ? "Assistant" : "Clinical tools"}
              </button>
            ))}
          </nav>
          <div className="top-meta">
            <span className="pill"><span className="dot" />{status}</span>
            <span className="pill">Jurisdiction <b>UK</b></span>
          </div>
        </div>
      </header>
      <main>{view === "assistant" ? <Consult /> : <Tools />}</main>
      <footer>
        Root Canon AI supports registered dental professionals and does not replace clinical judgement.
        Confirm doses against the current BNF or BNFC.
      </footer>
    </>
  );
}
