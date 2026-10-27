// Minimal, safe renderer for the answer format the model is instructed to use:
// paragraphs, bullet lists, bold, a "Clinical judgement:" line and [n] citations.
// No HTML from the model is ever injected into the page.

import { Fragment, type ReactNode } from "react";

function inline(text: string, onCite: (id: number) => void, key: string): ReactNode[] {
  const parts = text.split(/(\[\d{1,2}\]|\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    const cite = part.match(/^\[(\d{1,2})\]$/);
    if (cite) {
      const id = Number(cite[1]);
      return <button key={`${key}-${i}`} className="cite" onClick={() => onCite(id)} aria-label={`Source ${id}`}>{id}</button>;
    }
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={`${key}-${i}`}>{part.slice(2, -2)}</strong>;
    return <Fragment key={`${key}-${i}`}>{part}</Fragment>;
  });
}

export function AnswerBody({ text, onCite }: { text: string; onCite: (id: number) => void }) {
  const blocks: ReactNode[] = [];
  let list: string[] = [];
  const flush = () => {
    if (list.length) {
      const items = list;
      blocks.push(<ul key={`ul-${blocks.length}`}>{items.map((li, i) => <li key={i}>{inline(li, onCite, `li${blocks.length}-${i}`)}</li>)}</ul>);
      list = [];
    }
  };
  text.split(/\n+/).forEach((raw, index) => {
    const line = raw.trim();
    if (!line) return;
    if (/^[*\-•]\s+/.test(line)) { list.push(line.replace(/^[*\-•]\s+/, "")); return; }
    flush();
    if (/^>/.test(line)) {
      blocks.push(<p key={index} className="judgement">{inline(line.replace(/^>\s*/, ""), onCite, `q${index}`)}</p>);
    } else if (/^clinical judgement:/i.test(line)) {
      blocks.push(<p key={index} className="judgement"><b>Clinical judgement:</b>{inline(line.replace(/^clinical judgement:/i, ""), onCite, `j${index}`)}</p>);
    } else {
      blocks.push(<p key={index}>{inline(line, onCite, `p${index}`)}</p>);
    }
  });
  flush();
  return <div className="answer">{blocks}</div>;
}
