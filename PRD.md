# PrintBot — Product Requirements Document

## 1. Summary

PrintBot automates a walk-in print shop. Customers send a document to a Telegram (primary) or WhatsApp bot, choose print options with buttons, pay online, and the job goes straight to the shop's print queue. The shop owner manages orders, printers, pricing and customers from a web dashboard.

## 2. Problem

Walk-in print shops lose time and accuracy on: customers sending files over chat and describing options in free text, manual price quotes, cash handling, and operators re-typing job details into a print dialog. Result: queues, wrong prints, disputes over price and payment.

## 3. Goals and non-goals

**Goals**
1. A customer can go from file to paid print job in under two minutes, with no app install.
2. The price shown is exactly what is charged; paid jobs print exactly once.
3. The operator can see, track and trace every job (serial-stamped pages) without touching the customer chat.
4. One-command deployment on a shop PC.

**Non-goals (v1)**
- Binding, lamination, photo printing, or large format.
- Multi-shop or multi-tenant SaaS.
- Native customer mobile apps.
- Customer accounts or logins beyond their chat identity.

## 4. Users

| User | Needs |
|---|---|
| Customer | Send a file, pick options, pay, know when it's ready |
| Shop operator / admin | See the queue, handle failures and refunds, set prices, monitor printers |

## 5. Functional requirements

### 5.1 Customer bot
- FR-1 Accept PDF, DOC, DOCX, JPG, PNG; reject unsupported or unreadable files with a clear message.
- FR-2 Guided options with buttons: copies, colour or B&W, paper size, all pages or a specific page range, single or double sided. Typed input (e.g. "12" copies, "3-5,8") is parsed strictly; invalid input re-prompts.
- FR-3 Show an order summary with the total price before payment.
- FR-4 Pay via Razorpay payment link; in demo mode a "Pay (Demo)" button.
- FR-5 Notify on payment, print start, completion and failure.
- FR-6 Global commands at any step: CANCEL, RESTART, STATUS, HELP. The conversation never dead-ends.
- FR-7 A customer can only pay for, or cancel, their own order. Cancelling cancels the payment link.

### 5.2 Payments
- FR-8 Price is computed from admin-configured rules (paper × colour × sides × pages × copies).
- FR-9 Payment confirmation is idempotent: repeated taps or webhook retries release exactly one print.
- FR-10 Forged, unsigned, underpaid or wrong-order payment events never release a print.
- FR-11 Payment arriving after cancellation or expiry is flagged for refund. Admin can refund a paid order.
- FR-12 Expired payment links cancel the order and free the customer to start again.

### 5.3 Printing
- FR-13 Convert every upload to a printable PDF; apply page range and copies.
- FR-14 Stamp a unique serial (`PB-YYYYMMDD-NNNNNN`) on each printed page, once, without modifying the original upload. The stamp also carries the copy (`Copy n/m`), the sheet and side on double-sided jobs (`Sheet n/m F|B`) and the page (`Pg n/m`), so a loose page can be matched to its order, copy and sheet.
- FR-14a Every order gets a short pickup code (4 characters, e.g. `K7M2`, no look-alike characters). It is sent to the customer when the order is queued and when it is printed, shown in the dashboard, and printed in large type on a cover sheet on top of the stack for orders of 2 or more pages. The cover sheet can be switched off in dashboard Settings.
- FR-14b Copies are written out in the printable PDF so each is individually stamped; double-sided jobs pad odd-length documents with a stamped blank back page so every copy starts on a fresh sheet.
- FR-15 Jobs are queued in strict submission order; failed jobs can be retried without a new serial or double stamping.
- FR-16 Print through CUPS printers; a virtual printer for demo and test.

### 5.4 Admin dashboard
- FR-17 Login (JWT). All admin API routes and the live WebSocket require authentication.
- FR-18 Pages: Dashboard (analytics, live events), Orders (search, filter, detail, actions), Print Queue, Printers (sync, status), Pricing (edit rules), Customers, Settings (payment mode and channel status), Print Agents (pairing codes, status, revoke).
- FR-19 Live updates when orders change status.

### 5.5 Data and privacy
- FR-20 Uploaded and printable files for finished orders are deleted after a configurable retention period.
- FR-21 Webhook events are de-duplicated and expire after 90 days.

## 6. Non-functional requirements

| Area | Requirement |
|---|---|
| Deployment | `docker compose up --build` starts DB, API, dashboard and runs the test suite |
| Security | No secrets in the repo; production refuses demo payments; signed webhooks; least-privilege DB user |
| Reliability | Atomic state transitions; counters safe under concurrency; DB schema validation enforced |
| Performance | Bot replies within ~2 s for options; document conversion under ~15 s for typical files |
| Quality | Automated tests on real Mongo, including HTTP smoke tests and an end-to-end flow over real sample documents |

## 7. Success metrics
- Order completion rate: orders started → paid → printed.
- Median time from file received to payment.
- Print failure rate and refunds per 100 orders.
- Operator interventions per day (target: only failures and refunds).

## 8. Status (2026-10)

- Telegram flow, demo and Razorpay payment, admin dashboard, serial stamping, pickup codes and cover sheets, retention and schema validation are implemented.
- Test suite: 67 tests pass against real MongoDB in Docker.
- WhatsApp is implemented but lightly tested.

## 9. Risks and open questions
- Bot tokens or Razorpay keys leaked in docs or chat → rotate and keep them in env only.
- Sync DB and CUPS calls on the event loop limit concurrency; fine for one shop, needs work for load.
- Refunds are flagged and admin-initiated; whether to automate Razorpay refunds is undecided.
- Windows exe is unsigned: SmartScreen or antivirus may warn; code signing is undecided.
- WhatsApp needs a hardening and test pass before being promoted to a primary channel.
- Pricing rules for non-standard paper (A3, legal, thick stock) and discounts are not yet defined.
