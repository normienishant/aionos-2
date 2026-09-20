import type {
  AuditEntry,
  Conversation,
  Customer,
  SendMessageResponse,
} from "./types";

// The Next.js rewrite in next.config.mjs proxies /api/* to the FastAPI backend,
// so same-origin fetches work in both dev and prod.
async function get<T>(path: string): Promise<T> {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`);
  return res.json();
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
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
