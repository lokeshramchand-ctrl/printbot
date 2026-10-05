# PrintBot — Architecture

## 1. System overview

```
 Customer ──Telegram (long polling / webhook)──┐
          ──WhatsApp Cloud API webhook─────────┤
                                               ▼
                     ┌──────────────────────────────────────────┐
 Razorpay ──webhook─▶│ FastAPI backend (:8000)                  │◀── REST + WebSocket ── React dashboard
                     │  api/  → services/  → models (Mongo shim)│     (nginx :80)
                     └───────────────┬──────────────┬───────────┘
                                     │              │
                               MongoDB 7        CUPS (pycups) or
                               (auth on)        virtual printer
```

| Component | Tech | Notes |
|---|---|---|
| Backend | FastAPI, Python 3.12 | API, webhooks, Telegram long-polling task, retention job |
| Database | MongoDB 7 | Accessed through a SQLAlchemy-style shim (`app/database.py`) |
| Frontend | React 18, Vite, TypeScript, Tailwind | Admin dashboard, served by nginx |
| Documents | PyMuPDF, Pillow, python-docx, LibreOffice | Convert any upload to a printable PDF, count pages |
| Payments | Razorpay (or demo mode) | Signed webhook → shared `confirm_payment` |
| Printing | CUPS via pycups, or simulated | `USE_VIRTUAL_PRINTER` |

## 2. Deployment (`docker-compose.yml`)

- `mongo` — Mongo 7 with `--auth`; init script creates a least-privilege app user. Bound to `127.0.0.1:27017`.
- `backend` — waits for healthy Mongo, exposes `:8000`, `/health` reports DB and payment mode.
- `frontend` — nginx serving the Vite build on `:80`, proxying API calls.
- `tests` — one-shot suite against real Mongo (`printbot_test` DB) plus HTTP smoke tests and an end-to-end run over every file in `./testdata`.
- Volumes: `mongo_data`, `storage` (uploads and printable PDFs).
- `MONGODB_URI` is deliberately not read from `.env` in compose, so the stack can't be pointed at Atlas by accident.
- `ENV=production` refuses to boot with `PAYMENT_MODE=demo`.

## 3. Backend layout (`backend/app`)

- `main.py` — app, CORS from `CORS_ORIGINS`, startup: `ensure_schema()`, seed admin and pricing, start Telegram polling, retention job.
- `api/` — `auth`, `orders`, `printers`, `pricing`, `analytics`, `customers`, `settings`, `websocket`, `telegram_webhook`, `whatsapp_webhook`, `razorpay_webhook`.
- `services/`
  - `bot_state_machine.py` — the core; one router shared by both channels.
  - `telegram_polling.py`, `telegram_service.py`, `whatsapp_service.py`, `messenger.py` (channel-aware outbound).
  - `document_service.py` — PDF/DOC/DOCX/JPG/PNG → PDF, page count, page-range trimming.
  - `pricing_service.py` — `calculate_price(db, paper, color, sides, pages, copies)`.
  - `razorpay_service.py`, `payment_service.py` — payment links, `confirm_payment`.
  - `print_service.py` — printer sync, `submit_job`, `execute_print_job`.
  - `serial_service.py`, `pdf_stamp_service.py` — order serial and page stamp.
  - `websocket_service.py` — live dashboard events.
- `models/` — Customer, Order, PrintJob, Payment, Printer, PricingRule, OrderStatusHistory, Message, WebhookEvent, SerialCounter, Admin.
- `db_schema.py` — collection validators, indexes, TTLs.

## 4. Bot conversation

```
IDLE → WAITING_FOR_FILE → ASK_COPIES → ASK_COLOR → ASK_PAPER_SIZE → ASK_PAGES
     → (ASK_PAGE_RANGE) → ASK_SIDES → WAITING_FOR_PAYMENT → IDLE
```

- Global commands work in every state: CANCEL/STOP, RESTART/RESET//START, STATUS, HELP.
- Per-customer scratch data lives in `Customer.state_data` (JSON; reassign a copy and `flag_modified`).
- Input parsing is strict: invalid input re-prompts rather than defaulting; no state is a dead end.
- Buttons match on `callback_data` ids (`COPIES_1`, `COLOR_BW`, `PAPER_A4`, `PAGES_ALL`, `SIDES_DOUBLE`, `CANCEL_ORDER`, `DEMO_PAY_<order_id>`), which must stay stable.
- Duplicate Telegram updates are ignored; a customer can only pay their own order.

## 5. Order lifecycle

```
PAYMENT_PENDING ──(webhook / demo pay)──▶ PAID ──▶ QUEUED ──▶ PRINTING ──▶ COMPLETED
       │                                                             └────▶ PRINT_FAILED
       └──▶ CANCELLED / EXPIRED          (paid-after-cancel ⇒ flagged for refund)
```

- Every change is logged in `OrderStatusHistory`; dashboard clients get a WebSocket event.
- `payment_service.confirm_payment` performs an atomic `PENDING→PAID` claim (`find_one_and_update`). Double taps and webhook retries therefore print exactly once.
- Underpayment and a payment link belonging to another order are rejected.
- Order ids: `PRN-…`. Print serial: `PB-YYYYMMDD-NNNNNN`.

## 6. Serial numbering and stamping

- `serial_counters` holds one document per UTC day plus a `QUEUE_SEQ` document. `_atomic_increment` does a single `find_one_and_update` with `$inc`, so concurrent callers never get the same value. On first use of a key it inserts the row (with an integer `id`) and the unique index on `date_key` arbitrates a creation race.
- The serial is generated once per order and reused on retry. `queue_sequence` gives strict submission ordering across day boundaries.
- `pdf_stamp_service` stamps the serial on the printable PDF only, never the uploaded original, once (`serial_stamped_at`). It draws with `insert_text` at an explicit baseline, because `insert_textbox` fails silently when the text doesn't fit.

## 7. The Mongo shim

`SessionLocal` is a `MongoSession` that keeps SQLAlchemy-style models:

- One process-wide `MongoClient`; `mongomock://` gives an in-memory DB for fast tests.
- A per-session identity map. `commit()` writes only changed fields (`$set`).
- Integer ids come from an atomic counter (`next_id`).
- `==` and `in_` filters on own columns are pushed to Mongo. Everything else (`ilike`, `and_/or_`, relationships) is evaluated in Python over the loaded collection.
- Relationships are hydrated through a hardcoded map.
- Atomic transitions bypass the shim and use `db.database.<collection>` directly.

## 8. Database schema (`db_schema.py`)

- `$jsonSchema` validators are derived from the models (type, nullability, max length) plus `ENUMS` and `MINIMUMS`. A new status value must be added to `ENUMS`.
- Unique partial indexes (not sparse) for print serial, customer channel ids and the Razorpay payment id. TTL on `webhook_events` (90 days).
- `ensure_schema()` is idempotent and replaces legacy index definitions.
- **mongomock ignores validators and partial filters**, so only the compose run, against real Mongo, exercises them. Always run it before shipping DB changes.

## 9. Security

- Admin: JWT (python-jose) with bcrypt-hashed passwords. REST routes require auth. The WebSocket requires a valid token.
- Webhooks: Razorpay HMAC signature, WhatsApp `X-Hub-Signature-256`, Telegram secret header. `/webhooks/telegram/setup` is admin-only. Processed webhook events are de-duplicated.
- Uploads are not publicly served. Only whitelisted static paths are mounted.
- Finished orders' files are deleted by a retention job.
- Secrets come from environment variables only. Never commit `.env`. Rotate any token that has appeared in a README or chat.

## 10. Known gaps

- WhatsApp is implemented but far less exercised than Telegram.
- Handlers make synchronous DB and CUPS calls on the event loop; non-equality filters in the shim are O(collection).
- Telegram polling runs in the API process, so scaling to several replicas needs a webhook, or a single poller.
