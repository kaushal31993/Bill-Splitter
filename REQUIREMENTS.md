# Bill Splitter — Requirements

Status: draft for review
Last updated: 2026-07-24

---

## 1. Overview

A web application for splitting shared bills. The user uploads a receipt (photo or
PDF), the app extracts the line items automatically, the user assigns each item to
one or more people, and the app computes what every person owes — including a fair
share of tax and tip.

Multiple bills can be grouped into a single **event** (e.g. a weekend trip, a night
out), displayed as sections: Bill 1, Bill 2, and so on. Totals are computed per bill
and rolled up across the whole event.

Primary user: the person who paid. The app runs locally on their machine.

---

## 2. Scope decisions

| Decision | Choice |
|---|---|
| Deployment | Local only, via Docker Compose on the user's machine |
| Accounts / auth | None — single user |
| Data storage | PostgreSQL running locally in Docker |
| Bill input | Photo or PDF upload with automatic item extraction |
| Manual entry | Also supported — items can be added and edited by hand |
| Tax / tip / fees | Entered per bill, allocated proportionally to each person's item subtotal |
| Payer | Tracked per bill; defaults to the app owner, changeable |
| Multiple bills | Grouped into events, rendered as sections |
| Roster | Per-event — each event has its own set of people, added as needed |
| Locale | US — USD, `$1,234.56`, dates `MM/DD/YYYY` |
| Export | Excel (`.xlsx`) download of an event's split |
| Quality bar | Production-ready — validation, error handling, tests, reproducible deploy |

---

## 3. Architecture

```
┌─────────────────────┐
│  React + TypeScript │   Vite dev server / static build
│  (browser)          │
└──────────┬──────────┘
           │ HTTP/JSON
┌──────────▼──────────┐
│  FastAPI (Python)   │   REST API, extraction orchestration
└──────────┬──────────┘
           │
     ┌─────┴──────┐
     │            │
┌────▼─────┐  ┌───▼──────────────┐
│ Postgres │  │ Claude vision API│   receipt → structured JSON
│ (Docker) │  │ (external)       │
└──────────┘  └──────────────────┘
```

**Frontend** — React + TypeScript, Vite, Tailwind for styling, TanStack Query for
server state, Zod for form/response validation.

**Backend** — FastAPI on Python 3.12+, Pydantic v2 for schemas, SQLAlchemy 2.0 with
Alembic migrations.

**Database** — PostgreSQL 16, running in Docker, persisted to a named volume.

**Extraction** — the backend sends the uploaded receipt to a Claude vision model and
receives structured JSON (line items, quantities, prices, subtotal, tax, tip). The
API key lives server-side only and is never exposed to the browser. Exact model ID
selected at implementation time.

**Everything comes up with a single `docker compose up`** — Postgres, API, and web.

### Why a backend at all

The app is single-user and local, so the backend exists for two specific reasons:
the extraction API key must not ship to the browser, and PDF handling (text
extraction, page rasterisation) is far more robust in Python than in the browser.

---

## 4. Data model

```
Person                          -- the reusable directory of names
  id, name, is_owner (bool), archived (bool), created_at

Event
  id, name, created_at, notes

EventParticipant                -- which people are on this event's roster
  id, event_id, person_id, display_name

Bill
  id, event_id, label ("Bill 1"), merchant, bill_date,
  payer_id  → EventParticipant,
  tax_minor, tip_minor, fee_minor, discount_minor,
  source_file_path, source_type (image | pdf | manual),
  extraction_status (pending | ok | failed | manual),
  created_at

LineItem
  id, bill_id, name, quantity, unit_price_minor, total_minor,
  position, is_manual_override (bool)

ItemAssignment
  id, line_item_id, event_participant_id, weight (default 1)
```

**Two-level roster.** `Person` is a reusable directory of names so recurring people
can be picked from a list instead of retyped; `EventParticipant` is the actual roster
for a given event. Assignments and payers reference the participant, not the person,
so it is structurally impossible to assign an item to someone who isn't on that
event's roster. Adding a brand-new name creates both rows in one action — the UI
presents it as simply "add a person to this event".

**Money is stored as integers in cents** throughout — never
floats. Conversion to display strings happens at the presentation edge only. This is
non-negotiable for a money app; floating-point arithmetic on currency produces
off-by-a-cent errors that compound across items.

**`weight` on assignment** defaults to 1 for an equal split among the assigned
people. It exists so that "Alice counts as 2 shares" is possible later without a
migration, but the v1 UI only ever sets 1.

---

## 5. Functional requirements

### 5.1 People
- Each event has its own roster. Add names freely while setting up an event, and add
  more later — a person can join an event that already has bills.
- Names used before are offered as suggestions, so recurring people are one click
  rather than retyped, but nothing forces reuse.
- Rename a person within an event without affecting other events.
- One person is flagged as the owner (the app user); they are on every event's roster
  by default and are the default payer.
- A participant with existing assignments cannot be removed from the event until
  those assignments are reassigned — removal is blocked with an explanation rather
  than silently corrupting the totals.

### 5.2 Events
- Create an event with a name.
- An event contains one or more bills, ordered, displayed as sections.
- Event view shows the roll-up: per-person totals across all bills, and net
  settlement.

### 5.3 Bill upload and extraction
- Accept `.jpg`, `.jpeg`, `.png`, `.heic`, `.webp`, and `.pdf`.
- Enforce a maximum file size (default 15 MB) and validate the actual file type by
  content, not by extension.
- Text-based PDFs are parsed directly; scanned PDFs are rasterised and go through
  the vision path. Multi-page PDFs are supported.
- Extraction returns: merchant name, date, line items (name, quantity, unit price,
  line total), subtotal, tax, tip, total.
- **Extraction is never trusted blindly.** The user lands on a review screen showing
  every extracted item, editable inline, with the running subtotal compared against
  the extracted total. A mismatch is surfaced as a warning, not silently accepted.
- Extraction failure is recoverable: the bill is created empty and the user falls
  back to manual entry rather than losing the upload.
- Uploaded files are retained and viewable alongside the bill for later reference.

### 5.4 Item assignment
- Each line item is assigned to one or more people from the event roster.
- An item assigned to exactly one person is a private item — that person pays it in
  full.
- Bulk actions: assign all items to everyone, then adjust the exceptions. This is the
  common path — most items are shared by all, a handful are not.
- An item with no one assigned blocks bill completion and is flagged clearly.

### 5.5 Tax, tip, fees, and discounts
- Entered per bill. Pre-filled from extraction when available, always editable.
- Each is allocated to each person **in proportion to that person's item subtotal**
  for that bill. Discounts allocate the same way, as a negative amount.
- Allocation uses the largest-remainder method so allocated shares sum **exactly** to
  the entered amount — no lost or phantom cents.

### 5.6 Totals and settlement
- Per bill: each person's item subtotal, their tax/tip/fee share, and their bill
  total.
- Per event: each person's total across all bills.
- Because the payer can differ per bill, balances are netted across the event —
  "Raj owes you $84.00, you owe Priya $21.00" — rather than reported per bill.
- The common case (owner paid everything) collapses to a simple "each person owes
  you X" list, and the UI presents it that way rather than showing a settlement
  graph for a trivial case.

### 5.7 Excel export
- Export an entire event as a single `.xlsx` workbook, generated server-side with
  `openpyxl` and downloaded from the browser.
- **Summary sheet** — one row per person: their total across all bills, what they
  paid, and their net position (owes / is owed). Plus event name, date, and the
  grand total.
- **One sheet per bill** — a matrix mirroring the assignment screen: line items down
  the rows, people across the columns, each cell holding that person's share of that
  item. Below the items, rows for tax, tip, fees, and discount showing each person's
  allocated share, then a total row per person. Merchant, date, and payer in a header
  block.
- Values are written as **real numeric cells with a currency number format**, not
  pre-formatted strings, so the numbers can be summed and charted in Excel.
- Column totals in the sheet are written as live Excel `SUM` formulas, so the
  workbook visibly proves its own arithmetic rather than asking the reader to trust
  it.
- Dates formatted `MM/DD/YYYY`; filename `{event-name}-{MM-DD-YYYY}.xlsx`.

### 5.8 Editing
- Bills, items, assignments, tax/tip, and payer are all editable after creation.
- Any edit recalculates totals immediately.
- Deleting a bill or item recalculates the event roll-up.

---

## 6. The splitting math

Worked through explicitly, since this is the core of the app and the place where
bugs are most costly.

**Step 1 — split each item among its assignees.**
For item with total `T` and assignees `A`, each person's share is `T / |A|`, computed
in minor units. The remainder from integer division is distributed one unit at a time
to assignees in a deterministic order (by person ID), so the shares always sum
exactly to `T` and the same input always produces the same output.

**Step 2 — per-person item subtotal for the bill.**
`subtotal[p] = Σ (that person's share of every item on the bill)`
By construction, `Σ subtotal[p] = bill item total`.

**Step 3 — allocate tax, tip, fees, discounts.**
For each charge `C`, person `p` gets `C × subtotal[p] / Σ subtotal`. Fractional
remainders are assigned by the largest-remainder method so the allocations sum
exactly to `C`.

**Step 4 — per-person bill total.**
`total[p] = subtotal[p] + tax[p] + tip[p] + fees[p] − discount[p]`

**Step 5 — net across the event.**
For each bill, every non-payer's total is a debt to that bill's payer. Summing
across all bills gives each person's net position. Positive means they owe, negative
means they are owed.

**Worked example.** Bill of 10 items, 4 people (A/B/C/D), A paid.
5 items split 4 ways, 1 item split among B/C/D, 2 items split between A and B,
1 private item for C. Tax and tip are then layered on proportionally — so C, holding
a private item, carries a proportionally larger share of the tax than someone who
only shared the common items. This is the correct behaviour and matches how the
restaurant actually charged tax.

**Invariant, enforced by tests:** for every bill, the sum of all per-person totals
equals the bill's grand total, to the cent, for any combination of item assignments
and charge amounts.

---

## 7. Explicitly out of scope for v1

- **Simplified debts** — collapsing A→B→C chains into fewer transfers. Deliberately
  excluded: the netting is opaque to the people being asked to pay, and balances that
  can't be traced back to a specific bill invite arguments. Balances stay literal.
- **Recording settlements** — no marking a balance as paid and no payment history.
  The app reports what each person owes for a given event; tracking whether they
  actually handed the money over happens outside it.
- **Shareable text summary** — not wanted; the Excel export covers sharing.
- User accounts, authentication, multi-device sync
- Multiple currencies within one event, or currency conversion
- Payment integration — the app computes balances, it does not move money
- Mobile native apps (the web UI will be responsive, but that is all)
- Recurring or scheduled bills
- Importing a previously exported workbook (export is one-way)

---

## 8. Non-functional requirements

- **Correctness of money handling** — integer cents end to end, exhaustive unit tests
  on the splitting and allocation logic including remainder edge cases.
- **Locale** — US throughout: USD, currency rendered as `$1,234.56`, dates as
  `MM/DD/YYYY`, `America/New_York` as the default timezone for bill dates. Formatting
  goes through `Intl.NumberFormat` / `Intl.DateTimeFormat` with an explicit `en-US`
  locale rather than the browser default, so output does not change machine to
  machine.
- **Testing** — pytest for backend, with the splitting math covered thoroughly;
  Vitest plus React Testing Library for frontend logic and key flows.
- **Validation** — Pydantic on every request boundary; uploads validated by content
  type and size; clear structured error responses.
- **Error handling** — extraction failures, malformed PDFs, oversized uploads, and
  API timeouts all produce actionable messages and never leave a bill in a broken
  half-created state.
- **Reproducibility** — `docker compose up` brings up the full stack; Alembic
  migrations run on start; seed data available for development.
- **Configuration** — API keys and connection strings via environment variables, with
  a checked-in `.env.example` and no secrets in the repository.
- **Accessibility** — keyboard-navigable assignment UI, proper labels, adequate
  contrast. The assignment grid is the app's most-used screen and should be usable
  without a mouse.

---

## 9. Decision log

Every requirement is settled — there are no open questions.

| Question | Decision |
|---|---|
| Core purpose | Multi-bill events with per-item assignment; one-off and grouped both covered |
| Accounts | None — single user, local |
| Data storage | PostgreSQL in Docker, on the user's machine |
| Backend | FastAPI — justified by API-key secrecy and PDF handling |
| Bill input | Photo or PDF upload, auto-extracted, then reviewed and edited |
| Tax / tip / fees | Allocated proportionally to each person's item subtotal |
| Payer | Tracked per bill, defaults to owner, editable |
| Roster | Per-event, with a reusable name directory behind it |
| Locale | US — USD, `MM/DD/YYYY` |
| Excel export | In scope — summary sheet plus one matrix sheet per bill |
| Simplified debts | Out — confusing to the people being asked to pay |
| Text summary | Out — Excel export covers sharing |
| Recording settlements | Out — the app computes what is owed, not what was collected |
