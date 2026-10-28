import { useState } from "react";
import { sendFeedback, type FeedbackReason } from "../lib/api";

const REASONS: [FeedbackReason, string][] = [
  ["incorrect", "Incorrect"],
  ["outdated", "Outdated guidance"],
  ["missing_source", "Missing source"],
  ["unsafe", "Unsafe"],
  ["unclear", "Unclear"],
];

/** Thumbs up or down for an answer. Comments are redacted on the server before they are stored. */
export function Feedback({ requestId }: { requestId: string }) {
  const [state, setState] = useState<"idle" | "reasons" | "sent" | "error">("idle");
  const [reasons, setReasons] = useState<FeedbackReason[]>([]);
  const [comment, setComment] = useState("");

  const submit = (rating: "up" | "down", chosen: FeedbackReason[]) =>
    sendFeedback(requestId, rating, chosen, comment).then(() => setState("sent")).catch(() => setState("error"));

  if (state === "sent") return <p className="feedback-done">Thank you. Feedback is reviewed by the clinical safety team.</p>;
  if (state === "error") return <p className="feedback-done">Feedback could not be sent.</p>;

  return (
    <div className="feedback">
      {state === "idle" && (
        <>
          <span>Was this useful?</span>
          <button type="button" className="fb" aria-label="Helpful" onClick={() => submit("up", ["helpful"])}>Yes</button>
          <button type="button" className="fb" aria-label="Not helpful" onClick={() => setState("reasons")}>No</button>
        </>
      )}
      {state === "reasons" && (
        <form className="feedback-form" onSubmit={(e) => { e.preventDefault(); submit("down", reasons.length ? reasons : ["other"]); }}>
          <div className="drugs">
            {REASONS.map(([value, label]) => (
              <label key={value}>
                <input type="checkbox" checked={reasons.includes(value)}
                  onChange={(e) => setReasons((r) => e.target.checked ? [...r, value] : r.filter((x) => x !== value))} />
                <span>{label}</span>
              </label>
            ))}
          </div>
          <input className="feedback-comment" placeholder="Optional comment (no patient details)" value={comment}
            maxLength={1000} onChange={(e) => setComment(e.target.value)} aria-label="Comment" />
          <div className="feedback-actions">
            <button type="button" className="btn ghost" onClick={() => setState("idle")}>Cancel</button>
            <button type="submit" className="btn">Send</button>
          </div>
        </form>
      )}
    </div>
  );
}
