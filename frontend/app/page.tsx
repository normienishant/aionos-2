"use client";

import { useEffect, useRef, useState } from "react";
import CustomerSelector from "@/components/CustomerSelector";
import { api } from "@/lib/api";
import type { ChatMessage, Customer, ToolTrace } from "@/lib/types";

const QUICK_REPLIES: Record<string, string[]> = {
  SK4821X: [
    "I want a full cash refund.",
    "Rebook me on the next flight.",
    "I also want a free business-class upgrade on my return flight for the trouble. If you don't do it, I'm filing a formal complaint and considering legal action.",
  ],
  TR1190B: [
    "This is a huge delay. I want a hotel room since it's been such a long delay.",
    "What compensation do I get for this?",
    "4 hours of my life wasted. I'm going to file a formal complaint about this.",
  ],
  WL7742: [
    "I want a full night's hotel stay for this 6-hour delay.",
    "Move me to the earlier flight SK-311 and waive the ₹2,000 fare difference - I'm Platinum.",
    "What am I actually entitled to here?",
  ],
};

function TraceChips({ trace }: { trace: ToolTrace[] }) {
  if (!trace.length) return null;
  return (
    <div className="mt-2 space-y-1">
      {trace.map((t, i) => (
        <div
          key={i}
          className={`flex flex-wrap items-center gap-1.5 text-[11px] ${
            t.escalated ? "text-red-700" : "text-slate-500"
          }`}
        >
          <span className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-white">
            {t.tool}
          </span>
          {t.policy_reference && (
            <span className="rounded bg-skyline-50 px-1.5 py-0.5 font-medium text-skyline-700">
              {t.policy_reference}
            </span>
          )}
          {t.escalated && (
            <span className="rounded bg-red-100 px-1.5 py-0.5 font-semibold text-red-700">
              ESCALATED → human
            </span>
          )}
        </div>
      ))}
    </div>
  );
}

export default function ChatPage() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [mode, setMode] = useState<{ llm_active: boolean; provider: string } | null>(null);
  const [selected, setSelected] = useState<Customer | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [traces, setTraces] = useState<Record<number, ToolTrace[]>>({});
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.getCustomers().then(setCustomers).catch(() => setError("Cannot reach the backend. Is it running on port 8000?"));
    api.getMode().then(setMode).catch(() => {});
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  async function selectCustomer(c: Customer) {
    setError(null);
    try {
      const conv = await api.startConversation(c.pnr);
      setSelected(c);
      setMessages(conv.messages);
      setTraces({});
    } catch {
      setError("Could not start the conversation. Is the backend running?");
    }
  }

  async function send(text: string) {
    if (!selected || !text.trim() || busy) return;
    setBusy(true);
    setInput("");
    const optimistic: ChatMessage = {
      id: Date.now(),
      role: "customer",
      content: text,
      created_at: new Date().toISOString(),
    };
    setMessages((m) => [...m, optimistic]);
    try {
      const res = await api.sendMessage(selected.pnr, text);
      setMessages((m) => [...m.filter((x) => x.id !== optimistic.id), res.user_message, res.agent_message]);
      setTraces((t) => ({ ...t, [res.agent_message.id]: res.tool_trace }));
    } catch {
      setError("Message failed - is the backend running on port 8000?");
    } finally {
      setBusy(false);
    }
  }

  const escalated = Object.values(traces).flat().some((t) => t.escalated);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">Customer Chat</h1>
          <p className="text-sm text-slate-500">
            Pick a customer to start their scenario, then continue the conversation to test
            entitlements, denials and escalation paths.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {mode && (
            <span
              className={`rounded-full px-3 py-1 text-xs font-medium ${
                mode.llm_active ? "bg-emerald-100 text-emerald-800" : "bg-orange-100 text-orange-800"
              }`}
              title={
                mode.llm_active
                  ? "Gemini function calling is active"
                  : "No GEMINI_API_KEY set - deterministic fallback agent is answering (same tools/audit trail)"
              }
            >
              {mode.llm_active ? "● Gemini LLM live" : "● Offline fallback mode"}
            </span>
          )}
          <button
            onClick={async () => {
              await api.reset();
              setSelected(null);
              setMessages([]);
              setTraces({});
            }}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50"
          >
            Reset demo
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>
      )}

      <CustomerSelector customers={customers} selectedPnr={selected?.pnr ?? null} onSelect={selectCustomer} />

      {selected && (
        <div className="rounded-xl border border-slate-200 bg-white">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
            <div>
              <span className="font-semibold">{selected.name}</span>
              <span className="ml-2 text-xs text-slate-500">
                {selected.loyalty_tier} · PNR {selected.pnr}
              </span>
            </div>
            {escalated && (
              <span className="rounded-full bg-red-100 px-3 py-1 text-xs font-semibold text-red-700">
                ⚠ Escalated to human team
              </span>
            )}
          </div>

          <div ref={scrollRef} className="chat-scroll h-[46vh] space-y-3 overflow-y-auto p-4">
            {messages.map((m) => (
              <div key={m.id} className={m.role === "customer" ? "flex justify-end" : "flex justify-start"}>
                <div
                  className={`max-w-[75%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm ${
                    m.role === "customer"
                      ? "rounded-br-sm bg-skyline-500 text-white"
                      : "rounded-bl-sm bg-slate-100 text-slate-800"
                  }`}
                >
                  {m.content}
                  {m.role === "agent" && traces[m.id] && <TraceChips trace={traces[m.id]} />}
                </div>
              </div>
            ))}
            {busy && (
              <div className="flex justify-start">
                <div className="rounded-2xl rounded-bl-sm bg-slate-100 px-4 py-2.5 text-sm text-slate-400">
                  SkyLine Assist is thinking…
                </div>
              </div>
            )}
          </div>

          <div className="border-t border-slate-100 p-3">
            <div className="mb-2 flex flex-wrap gap-1.5">
              {(QUICK_REPLIES[selected.pnr] ?? []).map((q) => (
                <button
                  key={q}
                  onClick={() => send(q)}
                  disabled={busy}
                  className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs text-slate-600 hover:bg-slate-100 disabled:opacity-50"
                  title={q}
                >
                  {q.length > 58 ? q.slice(0, 58) + "…" : q}
                </button>
              ))}
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                send(input);
              }}
              className="flex gap-2"
            >
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={`Message as ${selected.name}…`}
                className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-skyline-500 focus:outline-none"
              />
              <button
                type="submit"
                disabled={busy || !input.trim()}
                className="rounded-lg bg-skyline-500 px-4 py-2 text-sm font-medium text-white hover:bg-skyline-600 disabled:opacity-50"
              >
                Send
              </button>
            </form>
          </div>
        </div>
      )}

      {!selected && customers.length > 0 && (
        <p className="text-center text-sm text-slate-500">
          ↑ Select a customer above to open their seeded conversation.
        </p>
      )}
    </div>
  );
}
