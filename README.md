# Bill Splitter

Split shared bills without arguing about the math.

Upload a photo or PDF of a receipt, the line items are read out automatically,
you tap which people shared each item, and the app works out what everyone owes
— including a fair share of tax and tip. Multiple bills group into a single
event (a dinner, a weekend, a trip) and settle together.

Runs entirely on your own machine. No accounts, no cloud database, nothing
leaves the network except the receipt you choose to have read.

---

## Contents

- [Features](#features)
- [How the splitting works](#how-the-splitting-works)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Using it from your phone](#using-it-from-your-phone)
- [Architecture](#architecture)
- [API reference](#api-reference)
- [Development](#development)
- [Testing](#testing)
- [Extraction cost](#extraction-cost)
- [Security](#security)
- [Troubleshooting](#troubleshooting)
- [Design decisions](#design-decisions)

---

## Features

### Reading receipts

- **Photo or PDF upload** — JPG, PNG, WEBP, GIF, HEIC, and PDF.
- **Automatic line-item extraction** using a Claude vision model. Not
  traditional OCR: receipts are exactly where glyph-level OCR struggles
  (multi-column layouts, abbreviated names, prices detached from the item they
  belong to) and a model that reads *layout* does far better.
- **Text-layer fast path.** Digitally generated PDFs — Instacart, Amazon,
  emailed invoices — carry an embedded text layer, which is read locally and
  sent as text instead of page images. Roughly 10× cheaper and more accurate.
  Scanned PDFs fall back to the vision path automatically.
- **Nothing is trusted blindly.** Every extracted line lands on an editable
  review screen, and the running total is compared against the receipt's printed
  total. A mismatch is surfaced as a warning, never silently accepted.
- **Failure is recoverable.** If extraction fails, the upload is still saved and
  attached to the bill; you just enter the items by hand. You never lose a file
  because a model had a bad day.
- **HEIC and rotation handled.** iPhone photos are converted, and EXIF
  orientation is applied — a sideways receipt reads badly, so it's straightened
  before it's sent.

### Splitting

- **Per-item assignment.** Tap the people who shared each item. Assign to
  everyone, to a subset, or to one person for something private.
- **Bulk actions.** "Everyone on everything", then adjust the exceptions —
  that's the common path. "Fill the unassigned only" preserves the exceptions
  you already set.
- **Tax, tip, fees, and discounts** are allocated in proportion to what each
  person actually ordered, not split evenly. Someone who ordered the steak pays
  more of the tax.
- **Exact to the cent.** Remainders are distributed deterministically, and a
  test-enforced invariant guarantees per-person totals sum to the bill total
  exactly, for any combination of items and charges.

### Events and settlement

- **Multiple bills per event**, shown as sections: Bill 1, Bill 2, …
- **Per-event roster.** Each event has its own set of people, backed by a
  reusable name directory so recurring people are one click.
- **Payer tracked per bill**, defaulting to you but editable. If different
  people paid different bills, balances are netted per pair across the event.
- **Deliberately not simplified.** A→B→C debt chains are *not* collapsed into
  fewer transfers — netting is opaque to the people being asked to pay, and a
  balance you can't trace back to a specific bill invites arguments.
- **Guard rails.** You can't remove someone who still has items assigned or is
  the payer on a bill; the app tells you what to fix instead of silently
  changing every total.

### Output

- **Excel export** — a summary sheet (who owes, who paid, net position) plus one
  sheet per bill laid out as a matrix: items down the rows, people across the
  columns. Values are **real numeric cells** with currency formatting, and
  column totals are **live `SUM` formulas**, so the workbook demonstrates its own
  arithmetic rather than asking the reader to trust it.

### Interface

- Responsive down to small phones — the item grid reflows into stacked cards
  rather than scrolling sideways.
- Light and dark mode, following the system setting.
- Keyboard-navigable assignment grid, proper labels, `prefers-reduced-motion`
  respected.
- US locale throughout: USD, `$1,234.56`, `MM/DD/YYYY`, pinned to an explicit
  `en-US` locale so output doesn't change from machine to machine.

---

## How the splitting works

Worth understanding, because it's the whole point of the app.

**Per bill:**

1. **Each item is split among its assignees.** For an item costing `T` shared by
   `n` people, each pays `T / n` in integer cents. The remainder is distributed
   one cent at a time in a deterministic order, so shares always sum to `T`
   exactly and the same input always produces the same output.
2. **Each person's item subtotal** is the sum of their shares.
3. **Tax, tip, fees, and discounts are allocated proportionally** to those
   subtotals, using the largest-remainder method so allocations sum to exactly
   the amount entered — no lost or invented cents.
4. **A person's bill total** = subtotal + tax + tip + fees − discount.

**Per event:** every non-payer's bill total is a debt to that bill's payer.
Debts are summed per pair of people across all bills, then netted against the
reverse direction, so "A owes B $30, B owes A $10" is reported once as "A owes
B $20".

**The invariant:** for any bill, with any combination of assignments and
charges, the sum of all per-person totals equals the bill's grand total to the
cent. This is asserted directly in the test suite, including against thousands
of randomized inputs.

> **Money is stored as integer cents everywhere** — never floats. Floating-point
> arithmetic on currency drifts by fractions of a cent and compounds across the
> line items of a bill. The only place a decimal appears is at the presentation
> edge.

---

## Quick start

### Requirements

- **Docker Desktop** (or Docker Engine + Compose v2). Nothing else — Python,
  Node, and PostgreSQL all run inside containers.
- Optionally an **Anthropic API key** for automatic receipt reading. Without it
  the app runs fine; you just type the items in yourself.

### Run it

```bash
git clone <your-repo-url>
cd bill-splitter
cp .env.example .env
```

Open `.env` and paste your key into `ANTHROPIC_API_KEY=` (skip this to run
without automatic extraction), then:

```bash
docker compose up -d
```

Open **http://localhost:5173**. On first run it asks your name — you're added to
every event by default and set as the default payer, both editable.

The database schema is created automatically on start; there is no separate
migration step.

### Stop it

```bash
docker compose down
```

Your data lives in a named Docker volume and survives restarts. To wipe
everything including the database and uploaded receipts:

```bash
docker compose down -v
```

---

## Configuration

All settings live in `.env` (copied from `.env.example`). Every one has a
working default, so the only line you normally touch is the API key.

| Variable | Default | What it does |
|---|---|---|
| `ANTHROPIC_API_KEY` | *(empty)* | Enables automatic receipt reading. Empty = manual entry only. |
| `EXTRACTION_MODEL` | `claude-haiku-4-5` | Model used to read receipts. See [Extraction cost](#extraction-cost). |
| `EXTRACTION_EFFORT` | `low` | Thinking depth. Ignored by 4.5-generation models, which don't accept it. |
| `PREFER_PDF_TEXT_LAYER` | `true` | Read a digital PDF's text layer instead of sending page images. Set `false` only to force the vision path when debugging. |
| `MAX_UPLOAD_MB` | `15` | Upload size limit. |
| `WEB_PORT` | `5173` | Host port for the web UI. |
| `API_PORT` | `8000` | Host port for the API (only needed for direct access or docs). |
| `DB_PORT` | `5433` | Host port for PostgreSQL. `5433` avoids clashing with a local Postgres on `5432`. |

After changing `.env`:

```bash
docker compose up -d --force-recreate api
```

Confirm extraction is on — this should report `"extraction_enabled": true`:

```bash
curl -s http://localhost:8000/api/config
```

---

## Using it from your phone

Both devices need to be on the same Wi-Fi. Find your machine's LAN address:

```bash
ipconfig getifaddr en0
```

(On Linux: `hostname -I | awk '{print $1}'`.) Then open
`http://<that-address>:5173` on your phone.

No extra configuration is needed — the web container proxies `/api` on the same
origin, so the phone only ever talks to one port.

Two caveats: the address is a DHCP lease and can change after a router reboot,
and **anyone on that network can reach the app** — see [Security](#security).

---

## Architecture

```
┌──────────────────────────┐
│  React + TypeScript      │   Vite build, served by nginx
│  (browser)               │   nginx also proxies /api → api:8000
└────────────┬─────────────┘
             │ HTTP/JSON  (money as integer cents)
┌────────────▼─────────────┐
│  FastAPI (Python 3.12)   │   REST API, splitting math, Excel export
└────────────┬─────────────┘
             │
   ┌─────────┴──────────┐
   │                    │
┌──▼──────────┐   ┌─────▼──────────────┐
│ PostgreSQL  │   │ Claude API         │   receipt → structured JSON
│ (Docker)    │   │ (only on upload)   │
└─────────────┘   └────────────────────┘
```

**Why there's a backend at all**, given this is a single-user local app: the
extraction API key must never ship to the browser, and PDF handling is far more
robust in Python. Everything else could have been client-side.

### Layout

```
.
├── docker-compose.yml          # postgres + api + web
├── .env.example                # copy to .env
├── REQUIREMENTS.md             # the spec this was built from
├── backend/
│   ├── app/
│   │   ├── money.py            # integer-cent helpers, largest-remainder allocation
│   │   ├── splitting.py        # the core math — pure functions, no ORM, no I/O
│   │   ├── extraction.py       # receipt → structured JSON
│   │   ├── excel.py            # openpyxl workbook builder
│   │   ├── models.py           # SQLAlchemy models
│   │   ├── schemas.py          # Pydantic request/response schemas
│   │   ├── services.py         # ORM ↔ splitting glue
│   │   └── routers/            # people, events, bills
│   ├── alembic/                # migrations
│   └── tests/                  # 141 tests
└── frontend/
    ├── src/
    │   ├── api.ts              # Zod schemas + typed client
    │   ├── format.ts           # en-US money/date formatting
    │   ├── index.css           # design tokens, light/dark
    │   ├── components/
    │   └── pages/
    └── nginx.conf
```

### Data model

```
Person              reusable directory of names
Event               a trip, dinner, or night out
EventParticipant    this event's roster  (Person × Event)
Bill                one receipt within an event
LineItem            one row on a bill
ItemAssignment      which participants share which item
```

Assignments and payers reference an **EventParticipant**, not a Person, so the
database itself makes it impossible to assign an item to someone who isn't on
that event's roster.

---

## API reference

Interactive docs at **http://localhost:8000/docs** while running.

All money crosses the wire as integer cents in fields ending `_cents`.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Liveness check |
| `GET` | `/api/config` | Whether extraction is enabled, upload limit, currency |
| `GET` | `/api/people` | List the name directory |
| `POST` | `/api/people` | Create a person (`is_owner` marks you) |
| `GET` | `/api/people/owner` | The app owner, or 404 before first-run setup |
| `GET` | `/api/events` | List events with totals |
| `POST` | `/api/events` | Create an event |
| `GET` | `/api/events/{id}` | Full event: roster, bills, items, computed totals |
| `PATCH` | `/api/events/{id}` | Rename an event |
| `DELETE` | `/api/events/{id}` | Delete an event and everything in it |
| `GET` | `/api/events/{id}/totals` | Computed breakdown only |
| `GET` | `/api/events/{id}/export.xlsx` | Download the workbook |
| `POST` | `/api/events/{id}/participants` | Add someone to the roster |
| `PATCH` | `/api/events/{id}/participants/{pid}` | Rename within this event |
| `DELETE` | `/api/events/{id}/participants/{pid}` | Remove (409 if they hold items or paid a bill) |
| `POST` | `/api/events/{id}/bills` | Create an empty bill |
| `POST` | `/api/events/{id}/bills/upload` | Upload a receipt and extract it |
| `PATCH` | `/api/bills/{id}` | Update label, merchant, date, payer, tax/tip/fees/discount |
| `DELETE` | `/api/bills/{id}` | Delete a bill |
| `GET` | `/api/bills/{id}/source` | Download the original upload |
| `POST` | `/api/bills/{id}/items` | Add a line item |
| `POST` | `/api/bills/{id}/assign` | Bulk-assign people to every item |
| `PATCH` | `/api/items/{id}` | Edit name, quantity, or total |
| `DELETE` | `/api/items/{id}` | Delete a line item |
| `PUT` | `/api/items/{id}/assignments` | Replace who shares an item |

---

## Development

The Docker setup is the supported path and needs no local toolchain. If you want
hot reload:

**Backend** (needs Python 3.12+):

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

docker compose up -d db                    # just the database
export DATABASE_URL=postgresql+psycopg://billsplitter:billsplitter@localhost:5433/billsplitter

.venv/bin/alembic upgrade head             # create the schema (the api container
                                           # normally does this on start)
.venv/bin/uvicorn app.main:app --reload
```

**Frontend** (needs Node 20+):

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api to :8000
```

Rebuild a container after changing dependencies:

```bash
docker compose build api && docker compose up -d api
```

---

## Testing

**Backend — 141 tests.** All of them are offline; the suite makes **zero API
calls** and costs nothing to run.

```bash
docker compose exec api python -m pytest -q
```

Coverage concentrates where mistakes are expensive:

- `test_money.py` — cent conversion, largest-remainder allocation, including
  3,000 randomized cases asserting allocations always sum exactly.
- `test_splitting.py` — equal splits, subsets, private items, proportional
  charges, per-pair netting, and the sum-to-total invariant under randomized
  bills.
- `test_api.py` — full request/response flows, roster guards, the Excel
  workbook's structure and live formulas.
- `test_extraction.py` — file sniffing, JSON tolerance, dollars-to-cents
  reconciliation, and error surfacing.

**Frontend — 16 tests:**

```bash
docker run --rm -v "$PWD/frontend":/app -w /app node:22-alpine \
  sh -c "npm install && npm test"
```

Type-check:

```bash
docker run --rm -v "$PWD/frontend":/app -w /app node:22-alpine \
  sh -c "npm install && npx tsc -b"
```

---

## Extraction cost

Only uploads cost anything; everything else is free. Measured on a real 18-item
Instacart PDF:

| Model | Cost per receipt |
|---|---|
| `claude-haiku-4-5` *(default)* | **~$0.005** |
| `claude-sonnet-5` | ~$0.022 |
| `claude-opus-5` | ~$0.037 |

Haiku produced item-for-item identical output to both larger models on that
receipt. Transcription is a reading task, not a reasoning one — paying a
frontier-model rate for it buys nothing. Move up a tier only if you hit receipts
Haiku misreads.

Two things keep the cost down, both on by default:

- **PDF text layer.** Sent as a document, a PDF is rasterised and billed as
  images. Read locally as text, the same receipt costs roughly a tenth as much.
- **`EXTRACTION_EFFORT=low`.** Deep thinking here mostly buys output tokens.

Every extraction logs its token usage and estimated cost:

```bash
docker compose logs api | grep "Extraction via"
# Extraction via claude-haiku-4-5 [pdf-text]: 1911 in / 723 out tokens ≈ $0.0055
```

> **Note on prompt caching:** it does not help this workload and is deliberately
> not implemented. The only stable prefix is a ~300-token system prompt, below
> the minimum cacheable size for every model, and the receipt itself differs
> every time. A cache breakpoint would silently never activate while writes cost
> 1.25×.

---

## Security

**This app has no authentication.** That is a deliberate design decision for a
single-user tool on your own machine, but it has consequences worth stating
plainly:

- Anyone who can reach the port can **read, edit, and delete everything**.
- On `localhost` only, that's fine. The moment you expose it to your LAN so a
  phone can use it, **everyone on that Wi-Fi has full access** — think twice on
  a shared flat, office, or guest network.
- **Do not port-forward this to the internet** or put it behind a public tunnel
  without adding authentication first.

Other notes:

- `.env` is git-ignored. Keep your API key out of commits — and if one ever
  lands in a public repo, rotate it immediately rather than deleting the commit.
- Uploaded receipts are stored unencrypted in a Docker volume.
- Uploads are validated by file *content*, not extension, and capped by size.
- The database is exposed on `DB_PORT` for convenience with default
  credentials. Remove that port mapping from `docker-compose.yml` if you don't
  need direct access.

---

## Troubleshooting

**`docker compose up` fails to connect to the Docker daemon**
Docker Desktop isn't running. Start it and wait for the whale icon to settle.

**"Automatic receipt reading is off"**
`ANTHROPIC_API_KEY` isn't set, or the API container hasn't picked it up. Set it
in `.env`, then `docker compose up -d --force-recreate api`, and check
`curl -s http://localhost:8000/api/config`.

**"Couldn't read this receipt automatically"**
The message shown is the API's own explanation. Common causes: an exhausted
credit balance, an invalid key, or a rate limit. Full detail including the
request ID:

```bash
docker compose logs api --tail 50
```

The upload is always saved regardless — add the items by hand.

**The printed total doesn't match the line items**
That warning is the app doing its job. Usually an item was misread, or the
receipt has a discount that didn't land in the discount field. Fix the numbers
inline; every field is editable.

**Port already in use**
Change `WEB_PORT`, `API_PORT`, or `DB_PORT` in `.env` and re-run
`docker compose up -d`.

**Phone can't reach the app**
Confirm both devices are on the same network, re-check the IP
(`ipconfig getifaddr en0` — DHCP leases change), and allow the incoming
connection if your firewall prompts.

**Reset everything**

```bash
docker compose down -v && docker compose up -d
```

---

## Design decisions

Choices made deliberately, recorded so they don't get quietly reversed:

| Decision | Why |
|---|---|
| Integer cents, never floats | Float arithmetic on currency drifts and compounds across a bill |
| Tax/tip proportional, not equal | Matches how the merchant actually charged; someone who ordered more owes more of it |
| Debts netted per pair, chains not collapsed | A minimal-transfer graph is opaque to the person being asked to pay |
| No settlement recording | The app computes what's owed, not whether it was collected |
| Extraction reviewed, never auto-accepted | A model misreading a price silently is worse than no extraction |
| Failed extraction still creates the bill | Losing the upload because a model failed is the worst outcome |
| Removing an encumbered participant is blocked | Deleting someone out from under a completed bill is how totals quietly go wrong |
| Splitting math is pure functions | No ORM or I/O in the math means it can be tested exhaustively |

The full specification this was built from — including what was deliberately
left out — is in [REQUIREMENTS.md](REQUIREMENTS.md).

---

## License

No license file is included. Add one before publishing if you want others to be
able to use this — without it, default copyright applies and nobody may
legally reuse the code.
