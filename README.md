# SkyLine Assist — AI Customer-Service Agent for Airline Disruptions

A customer-facing agentic AI for airline disruption handling, built for the
6-hour assignment exercise. It understands intent, asks only necessary
questions, computes every entitlement through a **deterministic rules engine**
(never LLM guesswork), executes allowed actions, escalates out-of-policy
requests to humans, and writes **every decision to an audit trail** with the
exact policy cited.

- **Chat UI:** select one of the 3 customers, talk to the agent, trigger the
  escalation paths live.
- **Audit & Admin view:** full transcripts + every tool call with the policy
  cited for each decision.
- **Zero-setup default:** local SQLite database; works with or without a
  Gemini API key (see "offline fallback" below).

---

## 1. One-command run

Prerequisites: **Python 3.11+** and **Node.js 18+**. Nothing else.

```bash
run_all.bat        # Windows
./run_all.sh       # macOS / Linux
```

That single command will:
1. create a Python virtualenv and install backend dependencies,
2. create `backend/.env` from `.env.example` (add your `GEMINI_API_KEY` here),
3. install frontend npm dependencies,
4. seed the database (3 customers + bookings + inventory) and start
   FastAPI on **http://localhost:8000**,
5. start Next.js on **http://localhost:3000** and open your browser.

| URL | What |
|---|---|
| http://localhost:3000 | Chat UI (pick Priya / Arvind / Meher) |
| http://localhost:3000/audit | Audit & admin view |
| http://localhost:8000/docs | FastAPI docs (raw API) |

**The only required env var is `GEMINI_API_KEY`** (get a free key at
https://aistudio.google.com/apikey and paste it into `backend/.env`). Without
a key the app still runs end-to-end using a deterministic fallback agent that
uses the *same tools and audit trail* — the UI shows which mode is active
("Gemini LLM live" vs "Offline fallback mode").

### Verify everything works (no API key needed)
```bash
cd backend && .venv\Scripts\activate && python test_scenarios.py   # Windows
cd backend && .venv/bin/python test_scenarios.py                    # macOS/Linux
```
Runs 38 deterministic checks: rules-engine boundaries (exactly 3h/5h,
Rs.1,500 vs Rs.1,501), all 3 scenario flows (refund, rebooking, denials,
escalations), guard rails (legal threats, prompt injection) and audit-trail
integrity, against a throwaway database. Exit code 0 = all pass.

Optional env vars (all defaulted): `GEMINI_MODEL` (default `gemini-3.8-flash`; the agent also falls back through a chain of newer flash models automatically if a model's free-tier quota is exhausted or retired),
`DATABASE_URL` (Postgres/Supabase, see below), `FRONTEND_ORIGIN`.

### Using PostgreSQL / Supabase instead of SQLite
Default is a local SQLite file (`backend/airline_agent.db`) so the demo runs
with zero setup. To use Postgres/Supabase, set in `backend/.env`:
```
DATABASE_URL=postgresql+psycopg://postgres:YOUR-PASSWORD@db.YOUR-REF.supabase.co:5432/postgres
```
The schema is created automatically on startup. Reset the demo from the UI
("Reset demo" button) or `POST /api/reset` to clear conversations/audit.

### Resetting the demo
The **Reset demo** button clears all conversations, messages and audit
entries (customers/bookings stay). To rebuild the DB from scratch:
delete `backend/airline_agent.db` and restart — the seed runs automatically.

---

## 2. Architecture & process flow

```
                        ┌──────────────────────────────────────────────┐
                        │                 NEXT.JS UI                   │
                        │  / (chat: customer selector + conversation)  │
                        │  /audit (transcripts + full action log)      │
                        └───────────────┬──────────────────────────────┘
                                        │ POST /api/conversations/{pnr}/messages
                                        ▼
                        ┌──────────────────────────────────────────────┐
                        │            FASTAPI BACKEND (Python)          │
                        │                                              │
   customer message ──► │  1. GUARD SCAN (deterministic, guard.py)     │
                        │     legal threat / prompt-injection regexes  │
                        │        │                                     │
                        │        ▼                                     │
                        │  2. LLM TURN (agent.py)                      │
                        │     Gemini 2.0 Flash + SYSTEM_PROMPT         │
                        │     + 10 tool declarations (native           │
                        │       function calling — no LangChain)       │
                        │        │                                     │
                        │        ▼                                     │
                        │  3. LLM DECIDES: call a tool?  ◄──────────┐  │
                        │     (this is the ONLY decision point)     │  │
                        │        │ yes                              │  │
                        │        ▼                                  │  │
                        │  4. TOOLS LAYER (tools.py)                │  │
                        │     • re-verifies everything from the DB  │  │
                        │     • calls the RULES ENGINE              │  │
                        │     • writes AUDIT LOG row (policy cited) │  │
                        │        │                                  │  │
                        │        ▼                                  │  │
                        │  5. RULES ENGINE (rules_engine.py)        │  │
                        │     100% deterministic functions:         │  │
                        │     get_delay_compensation(hours)         │  │
                        │     check_fare_waiver_allowed(amount)     │  │
                        │     get_cancellation_options(pnr)         │  │
                        │     validate_rebooking(...)  etc.         │  │
                        │        │                                  │  │
                        │        └── tool result ───────────────────┘  │
                        │            (loop back to the LLM, max 8      │
                        │             rounds, then the LLM answers)    │
                        │                                              │
                        │  ESCALATION BRANCH:                          │
                        │   • guard detects legal threat  ─┐           │
                        │   • rules engine says            ├──────►    │
                        │     must_escalate (R4 > ₹1,500)  │  call     │
                        │   • request is out-of-policy     │  escalate │
                        │     (upgrade, extra comp,        │  _to_human│
                        │      non-airline exception)      │  + flag   │
                        │                                  └──────────►│
                        │  6. reply saved to DB (messages + audit)     │
                        └──────────────────────────────────────────────┘
```

**Key design point (the "why"):** the LLM is the *intent parser and
conversationalist*; it NEVER computes compensation amounts or entitlements.
Every amount/threshold comes from `rules_engine.py`, every execution is
re-verified in `tools.py` against the database, and every tool call is
appended to the `audit_log` table with `(timestamp, pnr, customer_message,
agent_reasoning, tool_called, tool_args, policy_reference, action_taken,
escalated)`. Even the escalation guarantee is partly deterministic: if the
guard detects a legal/formal-complaint threat, the agent is *instructed* to
escalate, and if it still fails to, the backend escalates itself
(`agent.py`, "guard AFTER the LLM").

### The 10 tools

| Tool | Purpose |
|---|---|
| `lookup_booking(pnr)` | Fetch flight, route, schedule, status from the data pack |
| `get_customer_profile(pnr)` | Name, tier, contact, history + R5 loyalty benefits |
| `get_delay_compensation(hours)` | **R2** — exact entitlement for a delay length |
| `get_cancellation_options(pnr)` | **R1** — rebooking-vs-refund choice + flights + R3 refund terms |
| `check_fare_waiver_allowed(amount)` | **R4** — agent-limit check; `must_escalate` above ₹1,500 |
| `execute_rebooking(pnr, flight)` | **R1/R5** — free rebooking, re-verified; refuses if conditions unmet |
| `execute_refund(pnr)` | **R3** — full refund to ORIGINAL payment method, 7 business days |
| `issue_compensation(pnr, type)` | **R2** — meal voucher / lounge / delayed-hours hotel; recomputed from the stored delay, never from LLM-supplied numbers |
| `escalate_to_human(pnr, reason)` | Hand off to specialist team (mandatory for prohibited actions) |
| `log_action(pnr, action, policy_reference)` | Explicit audit note with policy citation |

---

## 3. File structure

```
airline-agent/
├── run_all.bat / run_all.sh       ONE-COMMAND runners
├── README.md                      this file
├── NOTES.md                       plain-language explainer + defence Q&A
├── backend/
│   ├── main.py                    FastAPI app (CORS, startup seed)
│   ├── requirements.txt
│   ├── .env.example               GEMINI_API_KEY / DATABASE_URL template
│   └── app/
│       ├── config.py              env config (DB, key, CORS)
│       ├── database.py            SQLAlchemy engine/session (SQLite or Postgres)
│       ├── models.py              Customer, Booking, RebookingInventory,
│       │                          Conversation, Message, AuditLog
│       ├── seed.py                GROUND-TRUTH data pack + assumed inventory
│       ├── rules_engine.py        ★ the 5 service rules as deterministic functions
│       ├── tools.py               ★ 10 tools + audit logging + re-verification
│       ├── guard.py               deterministic legal-threat / injection scan
│       ├── agent.py               ★ Gemini function-calling loop (the LLM decision point)
│       ├── offline_agent.py       no-API-key fallback (same tools + audit)
│       └── routes.py              /api endpoints (chat, audit, reset)
└── frontend/
    ├── next.config.mjs            /api/* proxy → FastAPI
    └── app/
        ├── page.tsx               chat UI (customer picker, quick replies, trace chips)
        ├── audit/page.tsx         audit & admin view
        └── components/CustomerSelector.tsx
```

---

## 4. Inputs, sources and assumptions

**Sources**
- 100% of the policy and customer data comes from the **provided data pack**
  (3 customer profiles, 4 booking rows, 5 service rules, allowed/prohibited
  actions, tone samples). No policy, customer detail or rule was invented.
- Tone of the replies follows the sample conversations in the brief
  (style only — not treated as policy).

**Assumptions (explicitly declared, none affect the 5 rules)**
1. **Rebooking inventory** is not in the data pack. To make `execute_rebooking`
   demoable we seeded plausible next-available Delhi→Goa flights (SK-206 /
   SK-210 / SK-214) and one higher-fare Delhi→Hyderabad flight (SK-311,
   fare +₹2,000) for Meher's scenario. Marked `ASSUMPTION` in `seed.py`.
2. **Fares and payment methods** are not in the data pack; seeded with
   plausible values. Payment method matters for R3 ("original payment method
   only") — each customer has one seeded ORIGINAL method.
3. **"More than 3 hours" / "more than 5 hours"** are strict inequalities:
   exactly 3h → voucher only; exactly 5h → voucher + lounge (hotel needs
   *more than* 5). Stated in `rules_engine.py` and consistent everywhere.
4. **Hotel covers the delayed hours only, never a full night** — encoded as a
   hard constant (`hotel_full_night` is always `False`); the data pack's
   "covering ONLY the delayed hours" is enforced in code.
5. **Non-airline-caused disruptions**: the data pack mentions only "customer
   missed the flight" as an example, so the agent treats any non-airline-caused
   exception request as escalation-required. No other cause is modelled.
6. **Business-day calendar** for the 7-day refund window is not modelled
   (the refund tool reports "within 7 business days" verbatim from R3).
7. **Concurrency/auth** are out of scope for the exercise; any user may open
   any of the 3 demo conversations.

---

## 5. Scenario walkthroughs (what the grader will test)

### Scenario 1 — Priya Nair (Gold, SK4821X, SK-204 cancelled)
| Step | What happens | Policy cited |
|---|---|---|
| Opener | She says her flight was cancelled and no one told her. Agent looks up the booking, shows empathy, presents the entitled **choice**: free rebooking within 24h **or** full refund. | **R1 Cancellation Rebooking Rule** |
| "I want a full cash refund." | `execute_refund` runs: full refund to her ORIGINAL payment method within 7 business days. | **R3 Refund Processing Rule** |
| Demands a free business-class upgrade "for the trouble" + threatens legal action/formal complaint | Upgrade = compensation beyond policy → NOT granted. Legal/formal-complaint threat → **immediate escalation** (deterministic guard, not LLM judgement). Agent stays empathetic. | PROHIBITED ACTIONS (compensation beyond policy; legal threats) |
| If she instead picks rebooking | `execute_rebooking` verifies status/24h window; Gold → priority rebooking flag (first access to next-available seats), **no extra compensation**. | **R1 + R5** |

### Scenario 2 — Arvind Kulkarni (Silver, TR1190B, 4h delay)
| Step | What happens | Policy cited |
|---|---|---|
| Opener | Agent looks up booking: SK-118 delayed 4h. | Data pack |
| Asks for a hotel "since it's been such a long delay" | `get_delay_compensation(4)` returns voucher + lounge only, **no hotel** (hotel needs >5h). Agent politely explains the 5h threshold and issues what he IS entitled to. | **R2 Delay Compensation Rule** |
| Any extra-compensation demand | Escalated (beyond policy). | PROHIBITED ACTIONS |

### Scenario 3 — Meher Kaur (Platinum, WL7742, 6h delay)
| Step | What happens | Policy cited |
|---|---|---|
| Opener | Agent looks up booking: SK-305 delayed 6h. | Data pack |
| Asks for a **full night's** hotel stay | `get_delay_compensation(6)` → hotel for the **6 delayed hours ONLY**, never a full night. Agent corrects her and issues voucher + lounge + delayed-hours hotel. | **R2 Delay Compensation Rule** |
| Asks to move to higher-fare SK-311 and **waive the ₹2,000 fare difference** (invoking Platinum status) | `check_fare_waiver_allowed(2000)` → `must_escalate: true` (agent limit ₹1,500). Agent does NOT approve; escalates to supervisor. Platinum gives priority rebooking, **not** extra waivers. | **R4 Fare Difference Rule** + **R5 Loyalty Tier Rule** |

### Where each decision is made (for the walkthrough)
- Delay thresholds / amounts → `backend/app/rules_engine.py::get_delay_compensation`
- ₹1,500 waiver limit → `backend/app/rules_engine.py::check_fare_waiver_allowed`
- Free-rebooking-vs-refund choice → `backend/app/rules_engine.py::cancellation_entitlement`
- Original-payment-method-only refund → `backend/app/rules_engine.py::refund_terms` +
  `backend/app/tools.py::tool_execute_refund`
- Priority rebooking for Gold/Platinum → `backend/app/rules_engine.py::get_loyalty_benefits`
- Escalation enforcement → `backend/app/guard.py` (threat scan) +
  `backend/app/agent.py` (mandatory escalation) +
  `backend/app/tools.py::tool_escalate_to_human` (records it)

---

## 6. AI tools used in building this

> **[EDIT THIS SECTION TO MATCH YOUR EXPERIENCE — draft below, adjust as you like]**

- **Codebuff (agentic AI coding agent):** generated the full codebase from the
  assignment brief — FastAPI backend, Next.js frontend, deterministic rules
  engine, Gemini function-calling loop, seed data, audit trail, self-test
  suite, and this documentation. All service rules were specified by the data
  pack; the agent encoded them as deterministic code rather than prompts.
- **Google Gemini 2.0 Flash (inside the product):** the agent's LLM — parses
  customer intent, decides which tools to call, and writes empathetic replies
  using native function calling. It never computes policy amounts itself.

*Edit the list above to add any other tools you personally used (ChatGPT,
Claude, etc.) and what you asked them to do.*

---

## 7. API quick reference

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/customers` | The 3 seeded customers + bookings + scenario openers |
| GET | `/api/mode` | Which agent mode is active (LLM / offline fallback) |
| POST | `/api/conversations/{pnr}` | Open (or resume) a conversation, seeded opener |
| POST | `/api/conversations/{pnr}/messages` | Send a customer message, get agent reply + tool trace |
| GET | `/api/audit` | Full audit trail (every tool call + policy cited) |
| GET | `/api/conversations` | All transcripts (admin view) |
| POST | `/api/reset` | Clear conversations + audit (customers stay) |
