// Typed client for the Root Canon AI API, including a server sent events reader
// for the streaming endpoint (EventSource cannot POST, so we parse the stream).

export type Provider = "anthropic" | "openai" | "ollama";

export interface Source {
  id: number;
  title: string;
  url: string;
  section: string | null;
  source: string;
  source_type: string;
  evidence: string;
  evidence_level: number;
  year: number | null;
  jurisdiction: string | null;
  snippet: string;
  score: number;
}

export interface Retrieval {
  dense_ms: number;
  sparse_ms: number;
  rerank_ms: number;
  candidates: number;
  returned: number;
}

export interface FinalEvent {
  answer: string;
  abstained?: boolean;
  out_of_scope?: boolean;
  grounded?: boolean;
  citation_coverage?: number;
  unsupported_numbers?: string[];
  latency_ms?: number;
  provider?: string;
}

export type StreamEvent =
  | { event: "meta"; data: { request_id: string; redactions: Record<string, number> } }
  | { event: "emergency"; data: { banner: string; codes: string[] } }
  | { event: "sources"; data: { sources: Source[]; retrieval: Retrieval } }
  | { event: "token"; data: { text: string } }
  | { event: "final"; data: FinalEvent };

export interface AskBody {
  question: string;
  history: string[];
  provider: Provider;
  patient_context?: string;
  filters?: { source_type?: string[]; min_evidence_level?: number };
}

const BASE = import.meta.env.VITE_API_URL ?? "";
const KEY = import.meta.env.VITE_API_KEY as string | undefined;

function headers(): HeadersInit {
  return { "Content-Type": "application/json", ...(KEY ? { "X-API-Key": KEY } : {}) };
}

export async function* askStream(body: AskBody, signal?: AbortSignal): AsyncGenerator<StreamEvent> {
  const response = await fetch(`${BASE}/v1/ask/stream`, {
    method: "POST", headers: headers(), body: JSON.stringify(body), signal,
  });
  if (!response.ok || !response.body) {
    throw new Error(response.status === 429 ? "Too many requests. Wait a moment and try again." :
      `The assistant is unavailable (HTTP ${response.status}).`);
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let boundary: number;
    while ((boundary = buffer.search(/\r?\n\r?\n/)) !== -1) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary).replace(/^\r?\n\r?\n/, "");
      let name = "message";
      const data: string[] = [];
      for (const line of block.split(/\r?\n/)) {
        if (line.startsWith("event:")) name = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
      }
      if (data.length) yield { event: name, data: JSON.parse(data.join("\n")) } as StreamEvent;
    }
  }
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${BASE}${path}`, { method: "POST", headers: headers(), body: JSON.stringify(body) });
  const json = await response.json();
  if (!response.ok) throw new Error(json.detail ?? `Request failed (${response.status})`);
  return json as T;
}

export interface Regimen {
  drug: string; population: string; dose: string; frequency: string; duration: string | null;
  indication: string; note: string; source_url: string; reviewed: string; verify_message: string;
}
export interface LALimit { product: string; weight_kg: number; max_mg: number; max_ml: number; max_cartridges: number; basis: string }
export interface Interaction { a: string; b: string; severity: string; effect: string }

export const tools = {
  regimen: (drug: string, age_years?: number) => post<Regimen>("/v1/tools/regimen", { drug, age_years }),
  localAnaesthetic: (product: string, weight_kg: number) => post<LALimit>("/v1/tools/anaesthetic", { product, weight_kg }),
  interactions: (drugs: string[]) => post<{ interactions: Interaction[]; note: string }>("/v1/tools/interactions", { drugs }),
};

export async function health(): Promise<{ status: string; chunks_indexed: number; llm_provider: string }> {
  const response = await fetch(`${BASE}/health`);
  return response.json();
}
