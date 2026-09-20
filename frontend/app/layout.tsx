import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "SkyLine Assist - Airline Disruption Agent",
  description:
    "Customer-facing AI agent for airline disruptions with a deterministic rules engine and full audit trail.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="bg-skyline-900 text-white">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
            <Link href="/" className="flex items-center gap-2 font-semibold">
              <span className="text-xl">✈️</span>
              <span>SkyLine Assist</span>
              <span className="rounded bg-skyline-700 px-2 py-0.5 text-xs font-normal text-skyline-100">
                AI Disruption Agent
              </span>
            </Link>
            <nav className="flex items-center gap-4 text-sm">
              <Link href="/" className="hover:text-skyline-100">
                Chat
              </Link>
              <Link href="/audit" className="hover:text-skyline-100">
                Audit &amp; Admin
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
