# 🖨️ PrintBot - Multi-Channel Automated Printing System

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/Frontend-React_18-61DAFB?style=for-the-badge&logo=react)](https://reactjs.org/)
[![Telegram](https://img.shields.io/badge/Messaging-Telegram_Bot_API-26A5E4?style=for-the-badge&logo=telegram)](https://core.telegram.org/bots/api)
[![WhatsApp](https://img.shields.io/badge/Messaging-WhatsApp_Cloud_API-25D366?style=for-the-badge&logo=whatsapp)](https://developers.facebook.com/docs/whatsapp/cloud-api)
[![Razorpay](https://img.shields.io/badge/Payment-Razorpay-0C2340?style=for-the-badge&logo=razorpay)](https://razorpay.com/)

**PrintBot** is a production-ready automated printing platform where **customers interact 100% through WhatsApp or Telegram (`@capstoneprinterbot`)**.

Customers upload documents, select print options via interactive buttons, and pay online via Razorpay. Print-shop staff manage all incoming jobs, queue status, pricing rules, and analytics from the **Admin Dashboard**.

---

## ⚡ Quick Start

### 1. Environment Setup

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Add your API keys to `.env`:

```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_from_botfather
WHATSAPP_ACCESS_TOKEN=your_whatsapp_access_token
WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id
WHATSAPP_VERIFY_TOKEN=your_verify_token
RAZORPAY_KEY_ID=your_razorpay_key_id
RAZORPAY_KEY_SECRET=your_razorpay_key_secret
RAZORPAY_WEBHOOK_SECRET=your_webhook_secret
```

---

### 2. Start Backend

```bash
cd backend
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

> **API Docs**: `http://localhost:8000/docs`

---

### 3. Start Frontend Dashboard

```bash
cd frontend
npm install
npm run dev
```

> **Admin Dashboard**: `http://localhost:5173` (User: `admin` | Pass: `admin123`)

---

### 4. Docker Setup (Alternative)

```bash
docker-compose up --build -d
```

---

## 🧪 Testing Commands

### Backend Unit Tests
```bash
cd backend
python -m pytest tests/ -v
```
This runs both the original suite (`tests/test_all.py`) and the print-serial
numbering suite (`tests/test_serial_numbering.py`), which specifically
covers: uniqueness of the serial and queue-position counters under real
concurrent threads, idempotency across retries/reprints (no duplicate
serial, no double-stamped PDF), rejection of double-executing a print
job, and that PDF stamping never alters the customer's original page
content, dimensions, or page count.

### WhatsApp Flow Simulation
```bash
cd backend
python scratch/test_e2e_simulation.py
```

### Telegram Flow Simulation
```bash
cd backend
python scratch/test_telegram_simulation.py
```

### Frontend Production Build
```bash
cd frontend
npm run build
```

---

## 🤖 Live Telegram Bot (`@capstoneprinterbot`)

1. Open Telegram and search for **`@capstoneprinterbot`**.
2. Tap **Start** or send **"Hi"**.
3. Upload any **PDF**, **DOC/DOCX**, **JPG**, or **PNG** file.
4. Select print preferences via inline buttons and complete payment.
5. Watch the order populate in real time on the **Admin Dashboard** (`http://localhost:5173`)!

---

## 🎨 Visual Theme

The admin dashboard uses a premium **black + gold** palette instead of the
generic blue/slate look most admin templates default to:

- Backgrounds run through Tailwind's `zinc` scale (near-black, neutral —
  warmer than pure `#000` so panels still read as distinct layers)
- A custom `gold` scale (`tailwind.config.js`) drives every primary
  action, active nav state, focus ring, and brand mark — `gold-500`
  (`#C9A227`) as the base interactive color, with buttons and active
  states using dark ink text *on* gold rather than white-on-gold, for a
  card/plaque feel rather than a flat "blue button" look
- Status colors are intentionally left as the standard emerald
  (success) / amber (pending) / rose (failed) convention — these carry
  universal meaning independent of brand color, so only the *live/active*
  state (printing, busy) and all primary actions were moved onto gold
- Headings use Playfair Display over Inter body text for a touch of
  editorial/premium contrast without hurting legibility at dashboard sizes

---

## 🔢 Print Serial Numbering & Queue Order

**Problem:** once several orders are queued and printed, staff pulling
finished pages off the printer/output tray have no fast way to tell
which physical page belongs to which order — especially with multiple
copies, multiple files, or several jobs printing back-to-back.

**Design chosen (see `backend/app/services/serial_service.py` and
`pdf_stamp_service.py` for the implementation):**

- **Level:** order-level, not per-copy or per-page. One serial
  identifies one order for its whole lifetime; every page of every copy
  of that order carries the same serial plus its own page number
  (`Pg 2/5`), which is enough to reassemble a stack correctly without the
  complexity of tracking per-copy identity through a printer's own
  built-in "N copies" duplication.
- **When generated:** the first time the order is submitted to the print
  queue (`print_service.submit_job`) — not at upload, not at payment.
  This is the point the identifier is actually needed and guarantees
  every queued order has a determinate serial before it can print.
- **Format:** `PB-YYYYMMDD-NNNNNN` — human-sortable by day, short enough
  to read at a glance, and immune to cross-day collisions since the date
  is baked into the value itself.
- **Uniqueness under concurrency:** a dedicated `serial_counters` table
  (one row per UTC day) is incremented with a single
  `UPDATE ... SET last_value = last_value + 1 RETURNING last_value`
  statement — the increment and the read of the resulting value happen
  in one atomic round trip, so two concurrent callers can never observe
  or claim the same number. This is verified directly in
  `test_daily_sequence_unique_under_concurrent_threads`, which fires 25
  real concurrent threads at the allocator and asserts 25 distinct
  results (an earlier version that split the UPDATE and the follow-up
  SELECT into two statements *did* produce duplicates under this test —
  the RETURNING form is what actually closes that race). The same
  mechanism, on a second counter row keyed `QUEUE_SEQ`, assigns a
  strictly increasing `PrintJob.queue_sequence` used to keep the queue's
  actual processing order auditable.
- **Idempotency across retries/reprints/force-print:** `Order.print_serial`
  is set exactly once; every subsequent call to `submit_job` for the same
  order (a failed job being retried, an admin re-printing, a force-print)
  reuses the existing value instead of minting a new one. The PDF is
  likewise stamped exactly once, guarded by `Order.serial_stamped_at` —
  a retry creates a new `PrintJob` row (so the attempt history stays
  auditable) but never re-stamps or double-stamps the file.
- **Where it's stamped:** directly on the *generated printable PDF*
  (`Order.printable_pdf_path`) via PyMuPDF — the same library
  `document_service` already uses to build that PDF from the customer's
  PDF/DOC/DOCX/JPG/PNG upload, so no new dependency was introduced. The
  customer's original upload (`Order.stored_file_path`) is never opened
  by the stamping step and is provably untouched
  (`test_original_uploaded_file_is_never_touched_by_stamping`).
- **Placement:** a small (6.5pt) grey line centered in the bottom margin
  of every page — `SERIAL | DATE | CUSTOMER-ID | Pg X/Y` — sitting inside
  the margin most printers already reserve, so it never overlaps,
  resizes, or clips the customer's own content. Verified directly:
  `test_stamp_preserves_original_content_and_page_geometry` re-opens the
  stamped PDF and asserts page count, page dimensions, and the original
  text are all unchanged.
- **Customer identifier:** never the raw phone number or chat ID — a
  short internal label like `W-102` (WhatsApp) or `T-57` (Telegram),
  built from the customer's internal record id.
- **Visibility:** shown in the Orders table, the Order Detail modal, and
  the Print Queue page in the admin dashboard, and included in the
  WhatsApp "ready for pickup" notification so the customer can quote it
  at the counter.
- **Existing databases:** MongoDB creates collections as documents are
  written. The backend creates the required unique and query indexes at
  startup, including the unique print serial, printer name, admin, webhook,
  and serial-counter indexes.

**Queue robustness fixes made alongside this feature:**
- `execute_print_job` now refuses to run a job that isn't `QUEUED`
  (previously only `CANCELLED` was excluded), which closes a real
  double-print hole if a job were re-triggered while already
  `PRINTING`/`COMPLETED`.
- `PrintJob.retry_count` is now actually incremented on failure, and a
  failed job clears the printer's `current_job_id`/status instead of
  leaving it stuck, so the next job can be assigned correctly.
- The Print Queue admin view (`GET /api/orders?status=QUEUED|PRINTING`)
  now sorts oldest-first for those two statuses specifically, so it
  reflects true submission order rather than most-recent-first.
- A pre-existing timestamp bug in `execute_print_job` (`job.started_at =
  db.query(Order).first().created_at.utcnow()` — using an unrelated
  order's timestamp) was fixed to `datetime.utcnow()`.

**Known limitations / deployment notes:**
- Set `MONGODB_URI` and `MONGODB_DATABASE` in `backend/.env` for local
  development and in the container environment for deployment.
- Physical multi-copy printing relies on the printer driver's own
  "copies" option (as before); PrintBot does not generate N distinct
  stamped PDFs per copy. All physical copies of one order therefore
  carry an identical stamp — sufficient to reunite a loose page with its
  order, but not to distinguish "copy 1 of 3" from "copy 2 of 3" of the
  same order if that level of granularity is ever needed.

---

## 📁 Project Structure

```
printerBot/
├── backend/
│   ├── app/
│   │   ├── api/             # FastAPI REST & Webhook routes
│   │   ├── models/          # SQLAlchemy database models
│   │   ├── schemas/         # Pydantic validation schemas
│   │   ├── services/        # Bot state machine, Document engine, Telegram/WhatsApp services
│   │   └── main.py          # FastAPI app entry point
│   └── tests/               # Backend test suite
├── frontend/
│   ├── src/
│   │   ├── pages/           # Admin Dashboard pages (Orders, Queue, Printers, Pricing)
│   │   └── services/        # Axios API client
├── docker-compose.yml       # Docker container orchestration
└── README.md
```

---

## 📄 License
MIT License
