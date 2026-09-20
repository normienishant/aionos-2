"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { AuditEntry, Conversation } from "@/lib/types";

export default function AuditPage() {
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [convos, setConvos] = useState<Conversation[]>([]);
  const [pnrFilter, setPnrFilter] = useState<string>("ALL");
  const [openConvo, setOpenConvo] = useState<number | null>(null);

  async function load() {
    const [a, c] = await Promise.all([api.getAudit(), api.getConversations()]);
    setAudit(a);
    setConvos(c);
  }

  useEffect(() => {
    load().catch(() => {});
  }, []);

  const pnrs = useMemo(
    () => Array.from(new Set(audit.map((a) => a.pnr).filter(Boolean) as string[])),
    [audit]
  );
  const filtered = pnrFilter === "ALL" ? audit : audit.filter((a) => a.pnr === pnrFilter);
  const escalatedCount = audit.filter((a) => a.escalated).length;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">Audit &amp; Admin View</h1>
          <p className="text-sm text-slate-500">
            Every tool call and decision, with the policy cited. {audit.length} entries ·{" "}
            <span className="font-medium text-red-600">{escalatedCount} escalations</span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={pnrFilter}
            onChange={(e) => setPnrFilter(e.target.value)}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm"
          >
            <option value="ALL">All customers</option>
            {pnrs.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
          <button onClick={load} className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50">
            Refresh
          </button>
        </div>
      </div>

      {/* Conversations */}
      <section className="rounded-xl border border-slate-200 bg-white">
        <h2 className="border-b border-slate-100 px-4 py-3 font-semibold">Conversation transcripts</h2>
        <div className="divide-y divide-slate-100">
          {convos.length === 0 && (
            <p className="px-4 py-4 text-sm text-slate-500">
              No conversations yet - start one on the Chat page.
            </p>
          )}
          {convos.map((c) => (
            <div key={c.id}>
              <button
                onClick={() => setOpenConvo(openConvo === c.id ? null : c.id)}
                className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-slate-50"
              >
                <span>
                  <span className="font-medium">{c.customer_name}</span>
                  <span className="ml-2 text-xs text-slate-500">
                    {c.loyalty_tier} · PNR {c.pnr} · {c.messages.length} messages
                  </span>
                </span>
                <span className="flex items-center gap-2 text-xs">
                  {c.escalated && (
                    <span className="rounded-full bg-red-100 px-2 py-0.5 font-semibold text-red-700">escalated</span>
                  )}
                  <span className="text-slate-400">{openConvo === c.id ? "▲" : "▼"}</span>
                </span>
              </button>
              {openConvo === c.id && (
                <div className="space-y-2 bg-slate-50 px-4 py-3 text-sm">
                  {c.messages.map((m) => (
                    <div key={m.id} className={m.role === "customer" ? "text-right" : "text-left"}>
                      <span
                        className={`inline-block max-w-[80%] whitespace-pre-wrap rounded-lg px-3 py-1.5 ${
                          m.role === "customer" ? "bg-skyline-500 text-white" : "bg-white text-slate-700"
                        }`}
                      >
                        {m.content}
                      </span>
                    </div>
                  ))}
                  {c.escalation_reason && (
                    <p className="text-xs text-red-600">Escalation reason: {c.escalation_reason}</p>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* Audit table */}
      <section className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <h2 className="border-b border-slate-100 px-4 py-3 font-semibold">Action log (audit trail)</h2>
        <table className="w-full min-w-[900px] text-left text-xs">
          <thead className="bg-slate-50 text-slate-500">
            <tr>
              <th className="px-3 py-2">#</th>
              <th className="px-3 py-2">Timestamp</th>
              <th className="px-3 py-2">PNR</th>
              <th className="px-3 py-2">Customer message</th>
              <th className="px-3 py-2">Agent reasoning</th>
              <th className="px-3 py-2">Tool called</th>
              <th className="px-3 py-2">Policy reference</th>
              <th className="px-3 py-2">Action taken</th>
              <th className="px-3 py-2">Escalated</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {filtered.map((a) => (
              <tr key={a.id} className={a.escalated ? "bg-red-50/60" : ""}>
                <td className="px-3 py-2 text-slate-400">{a.id}</td>
                <td className="px-3 py-2 whitespace-nowrap text-slate-500">
                  {new Date(a.timestamp).toLocaleTimeString()}
                </td>
                <td className="px-3 py-2 font-mono">{a.pnr}</td>
                <td className="max-w-[180px] truncate px-3 py-2" title={a.customer_message ?? ""}>
                  {a.customer_message}
                </td>
                <td className="max-w-[160px] truncate px-3 py-2 text-slate-500" title={a.agent_reasoning ?? ""}>
                  {a.agent_reasoning}
                </td>
                <td className="px-3 py-2 font-mono">{a.tool_called}</td>
                <td className="max-w-[180px] px-3 py-2">
                  <span className="rounded bg-skyline-50 px-1.5 py-0.5 font-medium text-skyline-700">
                    {a.policy_reference}
                  </span>
                </td>
                <td className="max-w-[220px] px-3 py-2" title={a.action_taken ?? ""}>
                  {a.action_taken}
                </td>
                <td className="px-3 py-2">
                  {a.escalated ? (
                    <span className="font-semibold text-red-600">YES</span>
                  ) : (
                    <span className="text-slate-400">no</span>
                  )}
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={9} className="px-3 py-4 text-center text-slate-500">
                  No audit entries yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}
