# PrintBot

Automated print-shop platform. Customers send a document to a Telegram or WhatsApp bot, choose print options with buttons, pay online through Razorpay, and the job goes straight into the shop's print queue. Shop staff manage orders, printers, pricing and customers from a web dashboard.

- Primary channel: Telegram (`@capstoneprinterbot`)
- Secondary channel: WhatsApp Cloud API (implemented, less exercised)
- Payments: Razorpay payment links with a signed webhook, or a demo mode for development
- Admin dashboard: React, served on port 80 in Docker or 5173 in development
- Database: MongoDB 7

## Contents

1. [Business context](#business-context)
2. [How it works](#how-it-works)
3. [Features](#features)
4. [Quick start](#quick-start)
5. [Configuration](#configuration)
6. [Payments](#payments)
7. [Admin dashboard](#admin-dashboard)
8. [Order lifecycle](#order-lifecycle)
9. [Print serial numbering](#print-serial-numbering)
10. [Security and privacy](#security-and-privacy)
11. [Testing](#testing)
12. [Project structure](#project-structure)
13. [Known limitations](#known-limitations)
14. [Further documentation](#further-documentation)
15. [License](#license)

## Business context

Walk-in print shops lose time and accuracy when customers send files over chat and describe their options in free text, when prices are quoted by hand, when cash must be handled, and when operators re-type job details into a print dialog. The result is queues, wrong prints, and disputes over price and payment.

PrintBot removes those steps. Its goals are:

1. A customer goes from file to paid print job in under two minutes, with no app install.
2. The price shown is exactly the price charged, and a paid job prints exactly once.
3. The operator can see, track and trace every job, including by a serial number stamped on each printed page, without touching the customer chat.
4. The whole system deploys on a shop PC with one command.

Out of scope for version 1: binding, lamination, photo printing, large format, multi-shop or multi-tenant use, native mobile apps, and customer accounts beyond the chat identity.

## How it works

```
Customer --> Telegram (long polling or webhook) --+
         --> WhatsApp Cloud API webhook ----------+
                                                   v
Razorpay --webhook--> FastAPI backend (:8000) <-- REST + WebSocket -- React dashboard
                       |             |
                    MongoDB 7     CUPS printer or virtual printer
```

Customer journey:

1. The customer opens the bot and sends `/start` or "Hi".
2. The customer uploads a PDF, DOC, DOCX, JPG or PNG file. Unsupported or unreadable files are rejected with a clear message.
3. The bot asks, with buttons: number of copies, colour or black and white, paper size, all pages or a page range, and single or double sided.
4. The bot shows an order summary with the total price.
5. The customer pays through a Razorpay payment link (or the demo button in development).
6. On confirmed payment the order is queued and printed. The customer is notified at payment, print start, completion and failure.
7. The customer collects the print and can quote the printed serial number at the counter.

Bot commands work at any step: `CANCEL` (or `STOP`), `RESTART` (or `RESET`, `/start`), `STATUS`, and `HELP`. The conversation never dead-ends: invalid input, such as an unparseable page range, re-prompts instead of falling back to a default.

## Features

Customer bot
- Accepts PDF, DOC, DOCX, JPG and PNG, converted to a printable PDF.
- Button-driven options with strict parsing of typed input (for example "12" copies or "3-5,8" pages).
- Price shown before payment, computed from admin-configured rules (paper size x colour x sides x pages x copies).
- A customer can only pay for or cancel their own order. Cancelling also cancels the payment link.

Payments
- Idempotent confirmation: repeated taps or webhook retries release exactly one print.
- Forged, unsigned, underpaid or wrong-order payment events never release a print.
- A payment arriving after cancellation or expiry is flagged for refund. Administrators can refund a paid order from the dashboard.
- Expired payment links cancel the order and let the customer start again.

Printing
- Page range and copies are applied to the printable PDF.
- Each printed page is stamped once with a unique order serial, without modifying the customer's original upload.
- Jobs are queued in strict submission order. Failed jobs can be retried without a new serial and without double stamping.
- Printing goes through CUPS (pycups), or a virtual printer for demo and tests.

Administration
- JWT login. All admin API routes and the live WebSocket require authentication.
- Live dashboard updates when orders change status.

## Quick start

### Option 1: Docker (recommended)

Requires only Docker. Put any documents you want the end-to-end test to use in `./testdata`.

```bash
docker compose up --build
```

This starts MongoDB 7 (authentication on, least-privilege application user), the backend on port 8000, the dashboard on port 80, and a one-shot `tests` service that runs the full suite against real MongoDB.

For CI, stop when the tests finish and propagate their exit code:

```bash
docker compose up --build --abort-on-container-exit --exit-code-from tests
```

| Service | URL |
|---|---|
| Dashboard | http://localhost |
| API | http://localhost:8000 |
| API documentation | http://localhost:8000/docs |
| Health check | http://localhost:8000/health |

Put overrides such as `TELEGRAM_BOT_TOKEN` in a root-level `.env` file. In Compose, `MONGODB_URI` is deliberately not read from `.env`, so the stack cannot be pointed at a hosted database by accident.

### Option 2: Local development

Prerequisites: Python 3.12, Node.js, and a MongoDB instance.

Backend:

```bash
cp .env.example backend/.env      # then edit backend/.env
cd backend
python -m venv venv
venv\Scripts\activate             # Windows; on Linux/macOS: source venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev                       # http://localhost:5173
```

The first start seeds an administrator and default pricing rules. In development the default login is `admin` / `admin123`. Change it before any real use; production refuses to start with this password.

### Try the bot

1. Set `TELEGRAM_BOT_TOKEN` and `PAYMENT_MODE=demo`. The backend starts Telegram long polling automatically when a token is present.
2. In Telegram, open your bot, send `/start`, then send a PDF.
3. Choose the options with the buttons and tap the demo pay button.
4. Expect a "Print complete" message, and see the order appear in the dashboard.

## Configuration

Settings are read from `backend/.env` (see `.env.example` for every option). Unknown variables are ignored. Never commit `.env`; this README intentionally contains no credentials.

| Variable | Purpose |
|---|---|
| `ENV` | `development` or `production`. Production enforces safe settings at startup. |
| `MONGODB_URI`, `MONGODB_DATABASE` | MongoDB connection. MongoDB is the only database. |
| `SECRET_KEY` | JWT signing key. In production, a random value of at least 32 characters. |
| `ADMIN_DEFAULT_USERNAME`, `ADMIN_DEFAULT_PASSWORD` | Seeded administrator account. |
| `CORS_ORIGINS` | Comma-separated allowed origins. A wildcard is rejected in production. |
| `TELEGRAM_BOT_TOKEN` | Bot token from BotFather. Enables long polling. |
| `TELEGRAM_WEBHOOK_SECRET`, `PUBLIC_BASE_URL` | Optional, for Telegram webhook mode. |
| `PAYMENT_MODE` | `demo` or `razorpay`. |
| `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET` | Required when `PAYMENT_MODE=razorpay`. |
| `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_APP_SECRET` | Optional WhatsApp channel. |
| `FILE_RETENTION_DAYS` | Days before files of finished orders are deleted (default 7). |
| `MAX_FILE_SIZE_MB`, `MAX_COPIES` | Upload and copies limits. |
| `CUPS_HOST`, `CUPS_PORT`, `USE_VIRTUAL_PRINTER` | Printing backend. The virtual printer simulates jobs. |
| `BUSINESS_NAME`, `BUSINESS_PHONE`, `PICKUP_ADDRESS` | Shown to customers in bot messages. |

## Payments

| `PAYMENT_MODE` | Customer experience | Intended use |
|---|---|---|
| `demo` (default) | The order summary has a `Pay (Demo)` button. Tapping it runs the same pipeline as a real payment: PAID, queued, printed, notified. No money moves. | Development and testing |
| `razorpay` | The customer receives a real Razorpay payment link. Payment is confirmed only by the signed webhook. | Production |

Both modes end in the same function, `payment_service.confirm_payment`, which performs an atomic PENDING-to-PAID claim before queueing, printing and notifying.

Going live with Razorpay:

1. Set `ENV=production`, `PAYMENT_MODE=razorpay`, a strong `SECRET_KEY`, a new `ADMIN_DEFAULT_PASSWORD`, explicit `CORS_ORIGINS`, and your real Razorpay keys.
2. In the Razorpay dashboard, create a webhook pointing to `<PUBLIC_BASE_URL>/webhooks/razorpay` with the events `payment_link.paid`, `payment_link.expired`, `payment_link.cancelled` and `payment.failed`.
3. Put the webhook secret in `RAZORPAY_WEBHOOK_SECRET`.

The webhook verifies the HMAC signature on every request, checks that the paid amount and payment link match the order, and is idempotent. Production refuses to boot with demo payments, a short or default `SECRET_KEY`, the default admin password, a wildcard CORS setting, or a configured WhatsApp channel without `WHATSAPP_APP_SECRET`.

Prices come from the pricing rules maintained on the Pricing page. Pricing for non-standard stock (A3, legal, thick paper) and discounts is not yet defined.

## Admin dashboard

Sign in at the dashboard URL. Pages:

| Page | Purpose |
|---|---|
| Dashboard | Analytics and live events |
| Orders | Search, filter, order detail, and actions (print, retry, cancel, refund), file download |
| Print Queue | Queued and printing jobs, oldest first |
| Printers | Sync CUPS printers, view status, test print |
| Pricing | Create and edit pricing rules |
| Customers | Customer list |
| Settings | Payment mode and channel status |

Order actions are available through `POST /api/orders/{order_id}/action` with `PRINT`, `RETRY`, `CANCEL` or `REFUND`. Printing is refused for orders that are unpaid, cancelled or refunded.

The interface uses a black and gold theme, defined in `frontend/tailwind.config.js`. Status colours stay emerald (success), amber (pending) and rose (failed).

## Order lifecycle

```
PAYMENT_PENDING --(webhook or demo pay)--> PAID --> QUEUED --> PRINTING --> COMPLETED
       |                                                          \--> PRINT_FAILED
       \--> CANCELLED / EXPIRED     (payment after cancellation is flagged for refund)
```

Every status change is recorded in `OrderStatusHistory` and broadcast to connected dashboards. Order ids look like `PRN-...`; print serials look like `PB-YYYYMMDD-NNNNNN`.

## Print serial numbering

Once several orders are queued, staff taking pages off the printer need a fast way to tell which page belongs to which order. PrintBot stamps a serial on every page.

- Level: one serial per order. Every page of every copy carries the same serial and its own page number (for example `Pg 2/5`).
- Generated: the first time the order is submitted to the print queue, not at upload or payment.
- Format: `PB-YYYYMMDD-NNNNNN`, sortable by day.
- Concurrency: the daily counter is a single atomic MongoDB `find_one_and_update` with `$inc`, so concurrent callers never receive the same number. A second counter, `QUEUE_SEQ`, gives each print job a strictly increasing `queue_sequence` that keeps the queue order auditable across day boundaries.
- Idempotency: the serial is set once per order and reused on retry, reprint or force-print. The PDF is stamped once, guarded by `serial_stamped_at`. A retry creates a new job record for history but never re-stamps the file.
- Where: on the generated printable PDF only, using PyMuPDF. The customer's original upload is never opened or modified.
- Placement: a small grey line centred in the bottom margin of each page, `SERIAL | DATE | CUSTOMER-ID | Pg X/Y`. It sits in the margin, so it does not change page size or the customer's content.
- Customer label: never the raw phone number or chat id. A short internal label such as `T-57` (Telegram) or `W-102` (WhatsApp) is used.
- Visibility: shown in the Orders table, the order detail dialog and the Print Queue, and included in the pickup notification to the customer.

Multi-copy printing relies on the printer driver's own copies option. All physical copies of one order carry an identical stamp, which is enough to reunite a loose page with its order but does not distinguish copy 1 from copy 2.

## Security and privacy

- Admin authentication uses JWT with bcrypt-hashed passwords. REST routes and the WebSocket require a valid token.
- Webhooks are verified: Razorpay HMAC signature, WhatsApp `X-Hub-Signature-256`, and the Telegram secret header. `/webhooks/telegram/setup` is admin-only. Processed webhook events are de-duplicated and expire after 90 days.
- Uploads are not served publicly; only whitelisted static paths are mounted.
- Files of finished orders are deleted after `FILE_RETENTION_DAYS` by a background retention job.
- The Docker database runs with authentication and a least-privilege application user. It is bound to `127.0.0.1` only.
- Secrets come from environment variables only. If a bot token or API key has ever appeared in a README, chat or commit, rotate it (BotFather `/revoke`, Atlas and Razorpay dashboards).

## Testing

Docker (real MongoDB, full suite):

```bash
docker compose up --build
```

This runs the unit and flow tests against real MongoDB (database `printbot_test`), HTTP smoke tests against the live backend, and an end-to-end run over every file in `./testdata`. Real MongoDB is required to exercise schema validators and partial, unique and TTL indexes.

Local, in-memory MongoDB (`mongomock`):

```bash
cd backend
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest tests -v
```

Coverage includes Telegram conversations with a fake client (copies, colour, paper, page ranges, sides), demo and Razorpay payment (forged, unsigned, underpaid and duplicate webhooks), order cancellation, the admin API, WebSocket authentication, file retention, serial numbering under concurrency, and the database schema.

Frontend production build:

```bash
cd frontend
npm run build
```

Never point tests at a hosted database.

## Project structure

```
printbot/
  backend/
    app/
      api/          REST and webhook routes
      models/       SQLAlchemy-style models persisted to MongoDB
      schemas/      Pydantic schemas
      services/     Bot state machine, documents, payments, printing, messaging
      database.py   Mongo session shim
      db_schema.py  Collection validators, indexes, TTLs
      config.py     Settings and startup validation
      main.py       Application entry point
    tests/          Backend test suite
  frontend/
    src/pages/      Dashboard pages
    src/services/   Axios API client
  docker/           MongoDB init script
  testdata/         Sample documents for the end-to-end test
  docker-compose.yml
  PRD.md
  ARCHITECTURE.md
```

## Known limitations

- WhatsApp is implemented but far less tested than Telegram, and needs a hardening pass before it becomes a primary channel.
- Handlers make synchronous database and CUPS calls on the event loop, and non-equality filters in the Mongo shim scan the collection. This is fine for a single shop but needs work under load.
- Telegram polling runs inside the API process. Running several replicas requires webhook mode or a single poller.
- Refunds are initiated by an administrator; automatic refunds are not implemented.
- Pricing for non-standard paper and discounts is not yet defined.

## Further documentation

- `PRD.md`: product requirements, goals, success metrics and open questions.
- `ARCHITECTURE.md`: components, deployment, the Mongo shim, schema and security design.
- `.env.example`: every configuration option.

## License

MIT License
