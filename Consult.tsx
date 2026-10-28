import { useCallback, useRef, useState } from "react";
import { askStream, type FinalEvent, type Provider, type Retrieval, type Source, type ToolCard } from "../lib/api";
import { AnswerBody } from "../lib/markdown";
import { exportConsult } from "../lib/export";
import { EvidenceTray } from "./EvidenceTray";
import { Feedback } from "./Feedback";
import { ToolCards } from "./ToolCards";

interface Turn {
  question: string;
  redactions: Record<string, number>;
  emergency: string | null;
  cards: ToolCard[];
  sources: Source[];
  answer: string;
  final: FinalEvent | null;
  error: string | null;
}

const CASES = [
  { tag: "Medically compromised", q: "Patient on apixaban twice daily needs a surgical extraction. What should they do with their dose?" },
  { tag: "Prescribing", q: "First choice antibiotic for a spreading dental abscess in an adult who is not allergic to penicillin?" },
  { tag: "Paediatric", q: "Amoxicillin dose for a dental abscess in a 3 year old" },
  { tag: "Cardiology", q: "Does a patient with a prosthetic heart valve need antibiotic prophylaxis before an extraction?" },
  { tag: "Prevention", q: "What fluoride toothpaste should a 2 year old use?" },
  { tag: "Urgent", urgent: true, q: "Swollen lips and wheeze after local anaesthetic. Suspected anaphylaxis, adrenaline dose?" },
  { tag: "Oral medicine", q: "When should I urgently refer a red and white patch in the mouth?" },
  { tag: "Medication safety", q: "Patient on Xarelto has toothache. Can I give Nurofen, and at what dose?" },
  { tag: "Local anaesthetic", q: "Maximum articaine for a 22 kg child?" },
];

export function Consult() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [retrieval, setRetrieval] = useState<Retrieval | null>(null);
  const [provider, setProvider] = useState<Provider>("anthropic");
  const [guidanceOnly, setGuidanceOnly] = useState(false);
  const [context, setContext] = useState("");
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [highlighted, setHighlighted] = useState<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const patch = (fn: (t: Turn) => Turn) => setTurns((all) => [...all.slice(0, -1), fn(all[all.length - 1])]);

  const ask = useCallback(async (question: string) => {
    const q = question.trim();
    if (!q || busy) return;
    setBusy(true);
    setSources([]);
    setRetrieval(null);
    const history = turns.map((t) => t.question);
    setTurns((all) => [...all, { question: q, redactions: {}, emergency: null, cards: [], sources: [], answer: "", final: null, error: null }]);
    abortRef.current = new AbortController();
    try {
      for await (const ev of askStream({
        question: q, history, provider,
        patient_context: context.trim() || undefined,
        filters: guidanceOnly ? { min_evidence_level: 6 } : undefined,
      }, abortRef.current.signal)) {
        if (ev.event === "meta") patch((t) => ({ ...t, redactions: ev.data.redactions }));
        else if (ev.event === "emergency") patch((t) => ({ ...t, emergency: ev.data.banner }));
        else if (ev.event === "tools") patch((t) => ({ ...t, cards: ev.data.cards }));
        else if (ev.event === "sources") {
          const found = ev.data.sources;
          setSources(found); setRetrieval(ev.data.retrieval); patch((t) => ({ ...t, sources: found }));
        }
        else if (ev.event === "token") patch((t) => ({ ...t, answer: t.answer + ev.data.text }));
        else if (ev.event === "final") patch((t) => ({ ...t, answer: ev.data.answer, final: ev.data }));
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") patch((t) => ({ ...t, error: (err as Error).message }));
    } finally {
      setBusy(false);
    }
  }, [busy, turns, provider, guidanceOnly, context]);

  const cite = (id: number) => {
    document.getElementById(`src-${id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    setHighlighted(id);
    window.setTimeout(() => setHighlighted(null), 1400);
  };

  const latest = turns[turns.length - 1];

  return (
    <div className="workspace">
      <aside className="rail">
        <div className="panel">
          <p className="label">Example consults</p>
          <div className="cases">
            {CASES.map((c) => (
              <button key={c.q} className={`case${c.urgent ? " urgent" : ""}`} onClick={() => ask(c.q)} disabled={busy}>
                <small>{c.tag}</small>{c.q}
              </button>
            ))}
          </div>
        </div>
        <div className="panel">
          <label className="label" htmlFor="context">Patient context</label>
          <textarea id="context" className="context" rows={3} value={context} maxLength={1500}
            placeholder="De identified: age band, conditions, allergies, medicines"
            onChange={(e) => setContext(e.target.value)} />
          <p className="note">Used for the medication safety screen. Identifiers are redacted before use.</p>
        </div>
        <div className="panel">
          <p className="label">Evidence filter</p>
          <label className="check"><input id="guidanceOnly" type="checkbox" checked={guidanceOnly} onChange={(e) => setGuidanceOnly(e.target.checked)} /> UK national guidance only</label>
        </div>
        <div className="panel">
          <p className="label">Language model</p>
          <div className="provider">
            {([["anthropic", "Claude", "default"], ["openai", "OpenAI", "switchable"], ["ollama", "Ollama", "on premises"]] as const).map(([value, name, hint]) => (
              <label key={value}>
                <input type="radio" name="provider" id={`prov-${value}`} checked={provider === value} onChange={() => setProvider(value)} /> {name} <small>{hint}</small>
              </label>
            ))}
          </div>
        </div>
      </aside>

      <section className="panel thread" aria-label="Consultation">
        <div className="thread-head">
          <div>
            <h1>Ask a clinical question</h1>
            <p>Every statement is tied to a numbered UK source. Identifiers are redacted before retrieval.</p>
          </div>
          {turns.some((t) => t.final) && !busy && (
            <button type="button" className="btn ghost small" onClick={() => exportConsult(turns)}>Export notes</button>
          )}
        </div>
        <div className="messages" aria-live="polite">
          {!turns.length && <p className="empty">Choose an example consult or type your own question.</p>}
          {turns.map((t, i) => (
            <div key={i} style={{ display: "contents" }}>
              <div className="msg-q">
                {t.question}
                {Object.keys(t.redactions).length > 0 && (
                  <span className="redact">Redacted before processing: {Object.entries(t.redactions).map(([k, v]) => `${k.toLowerCase().replace("_", " ")}${v > 1 ? ` ×${v}` : ""}`).join(", ")}</span>
                )}
              </div>
              <div className="msg-a">
                <div className="who"><b>Root Canon AI</b><span>{t.final?.provider ?? provider}</span></div>
                {t.emergency && <div className="banner" role="alert"><strong>Emergency</strong><span>{t.emergency}</span></div>}
                <ToolCards cards={t.cards} />
                {t.error ? <p className="note">{t.error}</p> : (
                  <>
                    <AnswerBody text={t.answer} onCite={cite} />
                    {!t.final && busy && i === turns.length - 1 && <span className="caret" aria-hidden="true" />}
                  </>
                )}
                {t.final && !t.final.out_of_scope && (
                  <div className="checks">
                    {t.final.abstained ? <span className="chip warn">Abstained: evidence below threshold</span> : (
                      <>
                        <span className={`chip ${(t.final.citation_coverage ?? 0) >= 0.8 ? "ok" : "warn"}`}>Citation coverage {Math.round((t.final.citation_coverage ?? 0) * 100)}%</span>
                        <span className={`chip ${t.final.unsupported_numbers?.length ? "warn" : "ok"}`}>
                          {t.final.unsupported_numbers?.length ? `Unverified figures: ${t.final.unsupported_numbers.join(", ")}` : "All figures matched to sources"}
                        </span>
                        {t.final.faithfulness != null && (
                          <span className={`chip ${t.final.faithfulness >= 0.8 ? "ok" : "warn"}`}
                            title={t.final.unsupported_claims?.length ? `Weakly supported: ${t.final.unsupported_claims.join(" | ")}` : "Every cited claim matches its sources"}>
                            Claim support {Math.round(t.final.faithfulness * 100)}%
                          </span>
                        )}
                        {t.sources.some((s) => s.superseded_by) && <span className="chip warn">Superseded guidance retrieved</span>}
                      </>
                    )}
                  </div>
                )}
                {t.final?.request_id && !t.final.out_of_scope && <Feedback requestId={t.final.request_id} />}
              </div>
            </div>
          ))}
        </div>
        <form className="composer" onSubmit={(e) => { e.preventDefault(); ask(draft); setDraft(""); }}>
          <label htmlFor="question" style={{ position: "absolute", left: -9999 }}>Question</label>
          <textarea id="question" rows={1} value={draft} placeholder="Ask about prescribing, medically compromised patients, prevention or emergencies"
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(draft); setDraft(""); } }} />
          {busy ? <button type="button" className="btn ghost" onClick={() => abortRef.current?.abort()}>Stop</button>
            : <button className="btn" type="submit">Ask</button>}
        </form>
      </section>

      <EvidenceTray sources={sources} retrieval={retrieval} latency={latest?.final?.latency_ms ?? null} highlighted={highlighted} />
    </div>
  );
}
