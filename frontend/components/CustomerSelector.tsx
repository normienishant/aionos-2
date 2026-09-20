"use client";

import type { Customer } from "@/lib/types";

const TIER_STYLES: Record<string, string> = {
  Gold: "bg-amber-100 text-amber-800 border-amber-300",
  Silver: "bg-slate-200 text-slate-700 border-slate-300",
  Platinum: "bg-violet-100 text-violet-800 border-violet-300",
};

function statusStyle(status: string) {
  const s = status.toLowerCase();
  if (s.includes("cancel")) return "text-red-600";
  if (s.includes("delay")) return "text-orange-600";
  return "text-emerald-600";
}

export default function CustomerSelector({
  customers,
  selectedPnr,
  onSelect,
}: {
  customers: Customer[];
  selectedPnr: string | null;
  onSelect: (c: Customer) => void;
}) {
  return (
    <div className="grid gap-4 md:grid-cols-3">
      {customers.map((c) => {
        const disrupted = c.bookings.find((b) => b.delay_hours !== null || b.status.toLowerCase().includes("cancel")) ?? c.bookings[0];
        const selected = selectedPnr === c.pnr;
        return (
          <button
            key={c.pnr}
            onClick={() => onSelect(c)}
            className={`rounded-xl border bg-white p-4 text-left transition hover:shadow-md ${
              selected ? "border-skyline-500 ring-2 ring-skyline-500" : "border-slate-200"
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="font-semibold">{c.name}</span>
              <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${TIER_STYLES[c.loyalty_tier] ?? ""}`}>
                {c.loyalty_tier}
              </span>
            </div>
            <div className="mt-1 text-xs text-slate-500">PNR {c.pnr}</div>
            {disrupted && (
              <div className="mt-3 rounded-lg bg-slate-50 p-2 text-xs">
                <div className="font-medium">
                  {disrupted.flight} · {disrupted.route}
                </div>
                <div className={statusStyle(disrupted.status)}>
                  {disrupted.status}
                </div>
              </div>
            )}
          </button>
        );
      })}
    </div>
  );
}
