import type {
  AuditEntry,
  Conversation,
  Customer,
  SendMessageResponse,
} from "./types";

// Empty default = same origin: in the single-service Docker deploy FastAPI
// serves this static frontend AND the API, so no CORS or proxy is involved at
// all. For the two-service deploy (Vercel frontend + Render backend) set
// NEXT_PUBLIC_API_URL to the backend URL; for local dev either run
// `npm run dev` alongside uvicorn on :8000 and pass
// NEXT_PUBLIC_API_URL=http://127.0.0.1:8000, or rely on the Next.js rewrite.
// NOTE: still avoid routing long agentic turns (>30s) through the Next.js dev
// proxy — set the env var for dev if the connection resets mid-turn.
const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`);
  return res.json();
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`POST ${path} failed: ${res.status}`);
  return res.json();
}

export const api = {
  getCustomers: () => get<Customer[]>("/api/customers"),
  getMode: () =>
    get<{ llm_active: boolean; provider: string }>("/api/mode"),
  startConversation: (pnr: string) =>
    post<Conversation>(`/api/conversations/${pnr}`),
  sendMessage: (pnr: string, content: string) =>
    post<SendMessageResponse>(`/api/conversations/${pnr}/messages`, { content }),
  getAudit: () => get<AuditEntry[]>("/api/audit"),
  getConversations: () => get<Conversation[]>("/api/conversations"),
  reset: () => post<{ ok: boolean }>("/api/reset"),
};
