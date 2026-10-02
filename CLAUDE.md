# PrintBot — CLAUDE.md

Automated print-shop platform. Customers talk to a bot on **Telegram** (`@capstoneprinterbot`) or
**WhatsApp**, upload a document, pick options with buttons, pay via **Razorpay**, and the job lands
in a print queue managed from a **React admin dashboard**.

## Stack
- **Backend** `backend/` — FastAPI 2.0, Python 3.12, PyMuPDF (`fitz`), Pillow, python-docx, httpx,
  razorpay SDK, python-jose + passlib/bcrypt (admin JWT), websockets.
- **DB** — MongoDB (Atlas, `MONGODB_URI`) via a **custom SQLAlchemy-to-Mongo shim** (see below).
- **Frontend** `frontend/` — React 18 + Vite + TypeScript + Tailwind (black/gold theme), axios.
- **Deploy** — `docker-compose.yml` (backend :8000, frontend nginx :80, a redis service nobody uses).

## Run
```bash
# backend (no venv is committed; create one)
cd backend && python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000     # docs: /docs
# frontend
cd frontend && npm install && npm run dev                # http://localhost:5173, admin / admin123
# tests
cd backend && python -m pytest tests -v
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
  ASK_PAPER_SIZE → ASK_PAGES → ASK_SIDES → WAITING_FOR_PAYMENT`. Per-customer scratch data is in
  `Customer.state_data` (must call `flag_modified` after mutating). Global commands: CANCEL/STOP,
  RESTART/RESET//START, STATUS, HELP. Buttons are matched by substring on `callback_data`/title.
- `services/telegram_polling.py` — getUpdates loop (offset in memory only). `telegram_service.py` /
  `whatsapp_service.py` are thin API adapters (`send_text_message`, `send_buttons`,
  `send_payment_message`, file download).
- `document_service.py` — converts PDF/DOC/DOCX/JPG/PNG to a printable PDF, counts pages.
- `pricing_service.py` — `PricingRule` rows; `calculate_price(db, paper, color, sides, pages, copies)`.
- `razorpay_service.py` — payment links; returns `success: False` (no fake URL) when keys are the
  `rzp_test_key_id` placeholder. Webhook marks order PAID and calls `print_service.submit_job`.
- `print_service.py` — printer sync, `submit_job` (serial + stamp + queue sequence),
  `execute_print_job` (CUPS via pycups, or simulated when `USE_VIRTUAL_PRINTER=True`).
- `serial_service.py` / `pdf_stamp_service.py` — order serial `PB-YYYYMMDD-NNNNNN`, stamped once on the
  *printable* PDF only (never the original upload). README documents the design in detail.
- `websocket_service.py` — broadcasts events to the dashboard.

## Order lifecycle
`PAYMENT_PENDING → (Razorpay webhook) PAID → QUEUED → PRINTING → COMPLETED | PRINT_FAILED`.
Status changes are logged in `OrderStatusHistory`. Order ids come from `utils.helpers.generate_order_id`
(`PRN-…`).

## The Mongo shim (read before touching DB code)
`app/database.py` keeps SQLAlchemy models (`Base`, `Column`, `relationship`) but `SessionLocal` is
`MongoSession`, which emulates `query/filter/order_by/first/all/count/scalar/add/commit/refresh`
by **loading whole collections into memory and filtering in Python**. Consequences:
- Only simple filters are supported (`==, !=, <, >, in_, ilike, and_/or_`); `join` is a no-op.
  Anything fancier silently returns wrong results — add support or use `db.database.<coll>` directly.
- `commit()` re-saves *every tracked object*; ids for int PKs are `count_documents + 1` (race-prone,
  can collide after deletes).
- Relationships are hydrated by a hardcoded map in `_hydrate_relationships`.
- Performance is O(collection) per query — fine for a campus shop, not for scale.
- Atomic counters use `find_one_and_update` (`serial_service.py`), not the shim.
- `get_db()` opens a new `MongoClient` per request/poll cycle.

## Testing — current status (verified 2026-10-02)
- `pytest tests` → **14 passed** (`test_all.py`, `test_serial_numbering.py`) in a fresh venv.
- **Caveat:** the tests build a SQLite DB (`sqlite:///./test_printbot.db`) and bypass `MongoSession`,
  so the Mongo shim, bot state machine, webhooks and API routes have **no automated coverage**.
- README mentions `backend/scratch/test_e2e_simulation.py` and `test_telegram_simulation.py`;
  **`backend/scratch/` does not exist**. Stray DBs (`printbot.db`, `sim_*.db`) are leftovers of that.
- Live-test checklist for the Telegram bot: start backend (polling starts automatically) → /start →
  send a PDF → click through copies/color/paper/pages/sides → expect order summary + pay button →
  verify order in dashboard. Payment step needs real Razorpay test keys (`rzp_test_…`, not the
  placeholder) and a public URL for the webhook (ngrok/cloudflared).

## Known gaps / bugs (found in analysis)
1. **"Specific pages" is a no-op**: `PAGES_SPECIFIC` is accepted but `pages_to_print` is always `"all"`
   (`bot_state_machine.py` `_handle_pages_input`, order creation); the printer never receives a range.
2. Copies are capped to buttons 1/2/3 (+ "5" substring); typing e.g. `12` is parsed as `1`.
   Substring matching in `_handle_copies_input`/`_handle_sides_input` is fragile (`"2"` anywhere → double).
3. `WAITING_FOR_PAYMENT` with no Razorpay config leaves the customer stuck (only CANCEL/RESTART help);
   the order stays `PAYMENT_PENDING`. Cancelling does not cancel the order or Razorpay link.
4. Razorpay webhook skips signature verification when the test placeholder key is set, or when the
   signature header is absent (`razorpay_webhook.py`) → forged "paid" events are accepted. Fix before prod.
5. No Telegram webhook secret check; CORS is `*` with credentials; default admin `admin/admin123` and
   default `SECRET_KEY` are used unless overridden.
6. Telegram polling: offset not persisted (re-processes on restart), updates handled serially, no
   `answerCallbackQuery` (buttons show a spinner), `Markdown` parse mode will fail on filenames with
   `_`/`*` and the failure is only logged.
7. No FILE_RETENTION cleanup job despite `FILE_RETENTION_DAYS`; no upload size check for
   `MAX_FILE_SIZE_MB`; `printbot.db`, uploads and processed PDFs sit in the repo tree.
8. `docker-compose.yml` ships an unused Redis; `app/services/migration_service.py` is a stub; README
   still says "SQLAlchemy models" / `printerBot/` layout in places.
9. `datetime.utcnow()` deprecation warnings (363 in test run).

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
