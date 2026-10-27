import { useEffect, useState } from "react";
import { tools, type Interaction, type LALimit, type Regimen } from "../lib/api";

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
