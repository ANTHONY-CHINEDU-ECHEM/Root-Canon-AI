import type { SafetyFlag, ToolCard } from "../lib/api";

const LABELS: Record<ToolCard["tool"], string> = {
  regimen: "Verified regimen",
  local_anaesthetic: "Local anaesthetic ceiling",
  adrenaline: "Emergency dose",
  safety_screen: "Medication safety screen",
};

function tone(severity: ToolCard["severity"]): string {
  if (severity === "contraindicated" || severity === "major" || severity === "emergency") return "danger";
  if (severity === "moderate" || severity === "caution") return "warn";
  return "ok";
}

function Flags({ flags }: { flags: SafetyFlag[] }) {
  return (
    <ul className="flags">
      {flags.map((f) => (
        <li key={`${f.rule_id}-${f.drugs.join("-")}`} className={`flag ${tone(f.severity)}`}>
          <b>{f.severity}</b>
          <span><strong>{f.title}.</strong> {f.message}{" "}
            {f.source_url && <a href={f.source_url} target="_blank" rel="noopener noreferrer">Guidance</a>}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** Deterministic tool results. These never come from the language model: they are looked up in the
 * reviewed formulary and rule files, so they are shown apart from the generated narrative. */
export function ToolCards({ cards }: { cards: ToolCard[] }) {
  if (!cards.length) return null;
  return (
    <div className="toolcards" aria-label="Verified tool results">
      {cards.map((card, i) => (
        <section key={`${card.tool}-${i}`} className={`toolcard ${tone(card.severity)}`}>
          <header>
            <span className="toolcard-kind">{LABELS[card.tool]}</span>
            <span className="toolcard-badge" title="Looked up deterministically, not generated">Deterministic</span>
          </header>
          <h3>{card.title}</h3>
          {card.tool === "safety_screen"
            ? <Flags flags={(card.data.flags as SafetyFlag[]) ?? []} />
            : <p className="toolcard-summary">{card.summary}</p>}
          <p className="toolcard-verify">
            {card.verify}
            {card.source_url && card.tool !== "safety_screen" && (
              <> <a href={card.source_url} target="_blank" rel="noopener noreferrer">Source</a></>
            )}
          </p>
        </section>
      ))}
    </div>
  );
}
