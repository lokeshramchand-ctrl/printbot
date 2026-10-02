# PrintBot — CLAUDE.md

Automated print-shop platform. Customers talk to a bot on **Telegram** (`@capstoneprinterbot`) or
**WhatsApp**, upload a document, pick options with buttons, pay via **Razorpay**, and the job lands
in a print queue managed from a **React admin dashboard**.

## Stack
- **Backend** `backend/` — FastAPI 2.0, Python 3.12, PyMuPDF (`fitz`), Pillow, python-docx, httpx,
  razorpay SDK, python-jose + passlib/bcrypt (admin JWT), websockets.
- **DB** — MongoDB (Atlas, `MONGODB_URI`) via a **custom SQLAlchemy-to-Mongo shim** (see below).
- **Frontend** `frontend/` — React 18 + Vite + TypeScript + Tailwind (black/gold theme), axios.
- **Print agents** — `agent/` (Flutter: Windows + Android) and `agent-windows/` (Python tray app, PyInstaller
  single exe `dist/PrintBotAgent.exe`, tkinter + pystray, PyMuPDF render + pywin32 GDI silent printing).
  Both speak the same `/api/agent/*` protocol.
- **Deploy** — `docker-compose.yml`: local **MongoDB 7 (auth on, least-privilege app user)**, backend :8000, frontend nginx :80, and a one-shot `tests` service.

## Run
```bash
# everything + tests, one command (needs only Docker; put documents to test with in ./testdata)
docker compose up --build
# CI variant: stop when tests finish and propagate their exit code
docker compose up --build --abort-on-container-exit --exit-code-from tests

# backend (no venv is committed; create one)
cd backend && python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000     # docs: /docs
# frontend
cd frontend && npm install && npm run dev                # http://localhost:5173, admin / admin123
# tests
cd backend && python -m pytest tests -v
# Windows agent
cd agent-windows && pip install -r requirements-dev.txt
python -m pytest tests -q            # 8 unit tests (pairing, claim, print+report, failure, revoked token, report retry)
python -m printbot_agent             # run from source
./build.ps1                          # -> dist\PrintBotAgent.exe (~40 MB, unsigned, no console)
```
Config comes from `backend/.env` (copy of root `.env`; see `.env.example`). Settings live in
`backend/app/config.py` (pydantic-settings; unknown vars ignored).

## Architecture (backend/app)
- `main.py` — app, CORS (`*`), mounts `/storage`, includes `api.all_routers`. Startup: create Mongo
  indexes, seed admin + default pricing, and **start Telegram long-polling if `TELEGRAM_BOT_TOKEN` is set**.
- `api/` — REST + webhooks: `auth`, `orders`, `printers`, `pricing`, `analytics`, `customers`,
  `settings`, `websocket`, `telegram_webhook` (`/webhooks/telegram`, `/setup`), `whatsapp_webhook`,
  `razorpay_webhook`.
- `services/bot_state_machine.py` — **the core**. One router (`_process_state_transition`) shared by
  both channels. Customer states: `IDLE → WAITING_FOR_FILE → ASK_COPIES → ASK_COLOR →
  ASK_PAPER_SIZE → ASK_PAGES → (ASK_PAGE_RANGE) → ASK_SIDES → WAITING_FOR_PAYMENT`. Per-customer scratch data is in
  `Customer.state_data` (must call `flag_modified` after mutating). Global commands: CANCEL/STOP,
  RESTART/RESET//START, STATUS, HELP. Buttons are matched by substring on `callback_data`/title.
- `services/telegram_polling.py` — getUpdates loop (offset in memory only). `telegram_service.py` /
  `whatsapp_service.py` are thin API adapters (`send_text_message`, `send_buttons`,
  `send_payment_message`, file download).
- `document_service.py` — converts PDF/DOC/DOCX/JPG/PNG to a printable PDF, counts pages.
- `pricing_service.py` — `PricingRule` rows; `calculate_price(db, paper, color, sides, pages, copies)`.
- `razorpay_service.py` / `payment_service.py` — payment links, signed webhook, shared `confirm_payment` (see Payments).
- `print_service.py` — printer sync, `submit_job` (serial + stamp + queue sequence),
  `execute_print_job` (CUPS via pycups, or simulated when `USE_VIRTUAL_PRINTER=True`).
- `serial_service.py` / `pdf_stamp_service.py` — order serial `PB-YYYYMMDD-NNNNNN`, stamped once on the
  *printable* PDF only (never the original upload). README documents the design in detail.
- `services/agent_service.py` + `api/agents.py` — **print agents** (PC/phone apps in `agent/`, Flutter). Dashboard creates an agent → one-time pairing code → app gets a bearer token (SHA-256 stored). `POST /api/agent/heartbeat` upserts printers (`Printer.agent_id`, `last_seen_at`; stale > 90 s = unreachable), `POST /api/agent/jobs/claim` atomically flips QUEUED→PRINTING for the agent's printers, `GET …/file`, `POST …/report` (COMPLETED/FAILED). `execute_print_job` never prints on agent printers locally; jobs wait QUEUED for the claim. Claimed jobs of a silent agent (10 min) are re-queued.
- `websocket_service.py` — broadcasts events to the dashboard.

### Windows agent (`agent-windows/printbot_agent`)
`api.py` (pair/heartbeat/claim/file/report client), `runner.py` (poll loop: claim → download → print → report; retries
the report after network drops), `printers.py` (enumerate printers, render PDF pages with PyMuPDF, GDI print via pywin32;
paper/duplex/colour set per job in DEVMODE, copies sent as repeated documents), `gui.py` (tkinter pairing/status window,
tray icon; closing hides to tray, tray Quit stops; "Start with Windows" = `HKCU\...\Run`), `config.py`
(`%APPDATA%\PrintBotAgent\config.json` holds server URL + token). A second launch exits (single instance).

## Order lifecycle
`PAYMENT_PENDING → (Razorpay webhook) PAID → QUEUED → PRINTING → COMPLETED | PRINT_FAILED`.
Status changes are logged in `OrderStatusHistory`. Order ids come from `utils.helpers.generate_order_id`
(`PRN-…`).

## The Mongo shim (read before touching DB code)
`app/database.py` keeps SQLAlchemy models (`Base`, `Column`, `relationship`) but `SessionLocal` is `MongoSession`:
- One process-wide `MongoClient` (`get_client()`); `mongomock://` URIs give an in-memory DB for tests.
- Per-session identity map; `commit()` writes only changed fields (`$set`) of objects that changed since load.
- Integer ids come from an atomic counter (`next_id`); order ids from `serial_service.allocate_order_id`.
- `==` / `in_` filters on own columns are pushed to Mongo; other filters (`ilike`, `and_/or_`, relationship columns)
  are evaluated in Python over the loaded collection. `join` is a no-op. Anything fancier: use `db.database.<coll>`.
- Relationships are hydrated by a hardcoded map in `_hydrate_relationships`.
- Atomic state flips (PENDING→PAID, cancel) use `find_one_and_update` on `db.database.orders` directly.

## Payments
`PAYMENT_MODE=demo` (default) → order summary has a `DEMO_PAY_<order_id>` callback button; `razorpay` → real payment
link + signed webhook. Both end in `payment_service.confirm_payment` (atomic PENDING→PAID claim, then queue/print/notify).
Production (`ENV=production`) refuses to boot in demo mode (`config.validate_settings`). Customer messaging always goes
through `services/messenger.py` (channel-aware). Telegram is the primary channel.

## Database schema
`app/db_schema.py` is the single source: collection `$jsonSchema` validators are *derived from the SQLAlchemy models* (types, nullability, max length) plus enums/minimums in `ENUMS`/`MINIMUMS`; unique **partial** indexes (not sparse: sparse still indexes explicit nulls) for print serial, customer channel ids, Razorpay payment id; TTL on `webhook_events` (90 d). `ensure_schema()` runs at startup, is idempotent, and replaces legacy index definitions. Adding a status value in code means adding it to `ENUMS`, or real Mongo rejects the write. mongomock ignores validators/partial filters, so those checks run only under compose (`TEST_MONGODB_URI`).

## Testing
- `docker compose up --build` runs the whole suite against **real Mongo** (`printbot_test` db) plus HTTP smoke tests on the live backend and the end-to-end file test over every file in `./testdata`.
- `cd backend && python -m pytest tests` — runs on in-memory Mongo (`MONGODB_URI=mongomock://…`, set in `tests/conftest.py`).
  Covers bot flows (fake Telegram), demo + Razorpay payment, admin API, WS auth, retention, serial numbering.
- Live Telegram checklist: start backend (polling starts automatically) → /start → send a PDF → buttons → tap
  *Pay (Demo)* → expect "Print complete" → check order in dashboard.
- Never point tests at Atlas; live runs use whatever `MONGODB_*` is in `backend/.env`.

## Known remaining gaps
- Windows agent has **not printed a real page** nor been paired against a live backend; the exe is unsigned
  (SmartScreen/antivirus may warn). Tested: unit tests, printer enumeration, DEVMODE settings accepted (no job submitted).
- WhatsApp path is implemented but far less exercised than Telegram.
- Handlers still make synchronous DB calls on the event loop; Mongo shim is O(collection) for non-equality filters.
- Telegram bot token must be rotated if it was ever pasted into a README/chat (BotFather `/revoke`).

## Security notes
- `.env` and `backend/.env` contain **real Atlas credentials and a Telegram bot token**. The root
  README also embeds a bot token (different from `.env`). Rotate via BotFather / Atlas and remove from
  the README. `.env` is gitignored but the folder is not a git repo yet — run `git init` carefully.
- Never print or commit secrets; reference variable names only.

## Conventions
- Services are module-level singletons (`print_service`, `telegram_service`, …).
- Handlers are `async`; DB/CUPS calls inside them are synchronous (blocks the event loop).
- Mutating `state_data` (JSON dict) requires reassigning a copy plus `flag_modified`.
- User-facing bot copy uses Telegram Markdown and emoji; keep button `callback_data` ids
  (`COPIES_1`, `COLOR_BW`, `PAPER_A4`, `PAGES_ALL`, `SIDES_DOUBLE`, `CANCEL_ORDER`) stable.
- Frontend: pages in `src/pages`, API client in `src/services/api.ts`, WebSocket in `src/context`.
  Gold palette defined in `tailwind.config.js`; status colors stay emerald/amber/rose.
