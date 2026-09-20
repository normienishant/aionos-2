import type {
  AuditEntry,
  Conversation,
  Customer,
  SendMessageResponse,
} from "./types";

// The browser talks to the FastAPI backend DIRECTLY (CORS is enabled for the
// frontend origin). Going through the Next.js dev-server proxy resets the
// connection on long agentic turns (LLM rounds can take >30s), so a direct
// call is the reliable path for both dev and hosted deployments.
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

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
