import { useEffect, useState } from "react";
import { tools, type Interaction, type LALimit, type Regimen, type ScreenResult } from "../lib/api";

const DRUGS = ["phenoxymethylpenicillin", "amoxicillin", "metronidazole", "ibuprofen", "paracetamol"];
const LA = ["Lidocaine 2% with adrenaline 1:80,000", "Articaine 4% with adrenaline 1:100,000", "Mepivacaine 3% plain", "Prilocaine 3% with felypressin"];
const IX = ["amoxicillin", "metronidazole", "clarithromycin", "ibuprofen", "miconazole", "fluconazole", "warfarin", "apixaban", "rivaroxaban", "aspirin", "methotrexate", "lithium", "simvastatin", "alcohol"];

export function Tools() {
  const [drug, setDrug] = useState(DRUGS[1]);
  const [age, setAge] = useState("34");
  const [regimen, setRegimen] = useState<Regimen | null>(null);
  const [regimenError, setRegimenError] = useState<string | null>(null);
  const [product, setProduct] = useState(LA[0]);
  const [weight, setWeight] = useState("22");
  const [limit, setLimit] = useState<LALimit | null>(null);
  const [selected, setSelected] = useState<string[]>(["metronidazole", "warfarin"]);
  const [hits, setHits] = useState<Interaction[]>([]);
  const [planned, setPlanned] = useState("ibuprofen");
  const [current, setCurrent] = useState("Xarelto");
  const [screenContext, setScreenContext] = useState("asthma");
  const [screen, setScreen] = useState<ScreenResult | null>(null);

  useEffect(() => {
    const split = (v: string) => v.split(",").map((x) => x.trim()).filter(Boolean);
    const plan = split(planned);
    if (!plan.length) { setScreen(null); return; }
    const timer = window.setTimeout(() => {
      tools.screen(plan, split(current), screenContext).then(setScreen).catch(() => setScreen(null));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [planned, current, screenContext]);

  useEffect(() => {
    const years = age === "" ? undefined : Number(age);
    tools.regimen(drug, years).then((r) => { setRegimen(r); setRegimenError(null); })
      .catch((e: Error) => { setRegimen(null); setRegimenError(e.message); });
  }, [drug, age]);

  useEffect(() => {
    const kg = Number(weight);
    if (kg >= 3 && kg <= 250) tools.localAnaesthetic(product.split(" ")[0], kg).then(setLimit).catch(() => setLimit(null));
  }, [product, weight]);

  useEffect(() => {
    if (selected.length >= 2) tools.interactions(selected).then((r) => setHits(r.interactions)).catch(() => setHits([]));
    else setHits([]);
  }, [selected]);

  return (
    <div className="tools">
      <div className="panel tool">
        <h2>Prescribing regimen</h2>
        <p className="sub">SDCEP dental regimens, looked up deterministically. Doses never come from the language model.</p>
        <div className="row">
          <div className="field"><label className="label" htmlFor="drug">Drug</label>
            <select id="drug" value={drug} onChange={(e) => setDrug(e.target.value)}>{DRUGS.map((d) => <option key={d}>{d}</option>)}</select></div>
          <div className="field"><label className="label" htmlFor="age">Age in years</label>
            <input id="age" type="number" min={0} max={110} step={0.5} value={age} onChange={(e) => setAge(e.target.value)} /></div>
        </div>
        <div className="result">
          {regimenError && <div className="ix moderate"><b>No band on file</b><span>{regimenError}</span></div>}
          {regimen && (
            <>
              <div className="big">{regimen.dose}</div>
              <dl className="kv">
                <dt>Frequency</dt><dd>{regimen.frequency}</dd>
                <dt>Duration</dt><dd>{regimen.duration ?? "as directed"}</dd>
                <dt>Population</dt><dd>{regimen.population}</dd>
                <dt>Indication</dt><dd>{regimen.indication}</dd>
                <dt>Note</dt><dd>{regimen.note}</dd>
              </dl>
              <div className="verify">{regimen.verify_message} <a href={regimen.source_url} target="_blank" rel="noopener noreferrer">Source</a>, reviewed {regimen.reviewed}.</div>
            </>
          )}
        </div>
      </div>

      <div className="panel tool">
        <h2>Local anaesthetic ceiling</h2>
        <p className="sub">Maximum dose by weight in mg, mL and 2.2 mL cartridges.</p>
        <div className="row">
          <div className="field"><label className="label" htmlFor="la">Product</label>
            <select id="la" value={product} onChange={(e) => setProduct(e.target.value)}>{LA.map((p) => <option key={p}>{p}</option>)}</select></div>
          <div className="field"><label className="label" htmlFor="kg">Weight in kg</label>
            <input id="kg" type="number" min={3} max={250} value={weight} onChange={(e) => setWeight(e.target.value)} /></div>
        </div>
        {limit && (
          <div className="result">
            <div className="big">{limit.max_cartridges} cartridges</div>
            <dl className="kv"><dt>Maximum</dt><dd className="mono">{limit.max_mg} mg · {limit.max_ml} mL</dd><dt>Basis</dt><dd>{limit.basis}</dd></dl>
          </div>
        )}
      </div>

      <div className="panel tool" style={{ gridColumn: "1 / -1" }}>
        <h2>Medication safety screen</h2>
        <p className="sub">What you plan to prescribe against the patient's medicines, conditions and allergies. Brand names are understood.</p>
        <div className="row three">
          <div className="field"><label className="label" htmlFor="planned">Planned, comma separated</label>
            <input id="planned" value={planned} onChange={(e) => setPlanned(e.target.value)} /></div>
          <div className="field"><label className="label" htmlFor="current">Patient takes</label>
            <input id="current" value={current} onChange={(e) => setCurrent(e.target.value)} /></div>
          <div className="field"><label className="label" htmlFor="sctx">Conditions and allergies</label>
            <input id="sctx" value={screenContext} onChange={(e) => setScreenContext(e.target.value)} /></div>
        </div>
        {screen && (
          <div style={{ display: "grid", gap: 8 }}>
            <p className="note" style={{ margin: 0 }}>Read as: planned <b>{screen.planned.join(", ") || "none"}</b>; patient takes <b>{screen.current.join(", ") || "nothing listed"}</b>.</p>
            {!screen.flags.length && (
              <div className="ix" style={{ background: "var(--guide-soft)" }}><b style={{ color: "var(--guide)" }}>No rule fired</b><span>{screen.note}</span></div>
            )}
            {screen.flags.map((f) => (
              <div key={`${f.rule_id}-${f.drugs.join("-")}`} className={`ix ${f.severity === "contraindicated" ? "major" : f.severity === "caution" ? "moderate" : f.severity}`}>
                <b>{f.severity[0].toUpperCase() + f.severity.slice(1)}: {f.title}</b>
                <span>{f.message} {f.source_url && <a href={f.source_url} target="_blank" rel="noopener noreferrer">Guidance</a>}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="panel tool" style={{ gridColumn: "1 / -1" }}>
        <h2>Interaction check</h2>
        <p className="sub">Select what you plan to prescribe and what the patient already takes.</p>
        <div className="drugs">
          {IX.map((d) => (
            <label key={d}>
              <input id={`ix-${d}`} type="checkbox" checked={selected.includes(d)}
                onChange={(e) => setSelected((s) => e.target.checked ? [...s, d] : s.filter((x) => x !== d))} />
              <span>{d}</span>
            </label>
          ))}
        </div>
        <div style={{ display: "grid", gap: 8 }}>
          {selected.length >= 2 && !hits.length && (
            <div className="ix" style={{ background: "var(--guide-soft)" }}><b style={{ color: "var(--guide)" }}>No interaction in the curated dental set</b><span>This is not proof of safety. Check the BNF.</span></div>
          )}
          {hits.map((h) => (
            <div key={`${h.a}-${h.b}`} className={`ix ${h.severity}`}><b>{h.severity === "major" ? "Major" : "Moderate"}: {h.a} with {h.b}</b><span>{h.effect}</span></div>
          ))}
        </div>
      </div>
    </div>
  );
}
