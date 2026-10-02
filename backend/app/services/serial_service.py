"""
Print serial numbering.

Design summary (see README.md "Print Serial Numbering" section for the
full write-up of alternatives considered):

- Identifier is generated ORDER-level, the first time an order is
  submitted to the print queue (submit_job) — not at order creation
  and not per-copy/per-page. One serial identifies one order for its
  entire lifetime, which is what lets a staff member reunite a loose
  physical page with the right customer regardless of which copy or
  which retry produced it.
- Generation is idempotent: Order.print_serial is set exactly once and
  reused on every retry, reprint, or force-print of that order. Retrying
  a failed job never mints a second serial for the same order.
- Uniqueness + ordering under concurrency is guaranteed by a single
  atomic ``UPDATE serial_counters SET last_value = last_value + 1``
  statement per allocation, scoped to the current UTC date. This relies
  on the database's own write-serialization (row-level locking on
  Postgres, the single-writer lock on SQLite) rather than an
  application-level lock, so it stays correct across multiple worker
  processes and survives restarts — there is no in-memory counter that
  could reset or drift.
- Format: ``PB-YYYYMMDD-NNNNNN`` — a date-based prefix (immediately
  human-sortable and tells staff which day's batch a page belongs to)
  plus a 6-digit zero-padded sequence that resets each day so numbers
  stay short. The date component also means two different days can
  never collide even if the sequence table were ever reset.
- A second, non-date-scoped counter (key "QUEUE_SEQ") assigns a
  strictly increasing ``queue_sequence`` to every PrintJob at creation
  time. This is what the queue is actually ordered and audited by —
  it is independent of the human-readable serial so that queue
  ordering survives even across a day boundary.
"""
from datetime import datetime, timezone
from pymongo import ReturnDocument
from app.config import settings
from app.models.order import Order


def _atomic_increment(db, counter_key: str) -> int:
    """
    Atomically increments (and, if necessary, creates) the counter row
    identified by ``counter_key`` and returns the new value.

    The UPDATE...RETURNING is a single statement that both performs the
    increment and reads back the resulting value in one round trip. That
    matters: an UPDATE followed by a *separate* SELECT would leave a gap
    where a second concurrent caller's UPDATE+commit could land in
    between, and both callers would then read back the same (the second
    caller's) value — silently producing a duplicate serial despite each
    individual UPDATE being correctly atomic. RETURNING closes that gap
    by handing back exactly the row this statement produced, atomically.
    """
    result = db.database.serial_counters.find_one_and_update(
      {"date_key": counter_key},
      {
        "$inc": {"last_value": 1},
        "$set": {"updated_at": datetime.now(timezone.utc)},
        "$setOnInsert": {"date_key": counter_key},
      },
      upsert=True,
      return_document=ReturnDocument.AFTER,
    )
    if not result:
      raise RuntimeError(f"Unable to allocate serial counter for key={counter_key!r}")
    return result["last_value"]


def allocate_daily_sequence(db, when: datetime = None) -> str:
    """Allocates the next PB-YYYYMMDD-NNNNNN serial for the given UTC day."""
    when = when or datetime.now(timezone.utc)
    date_key = when.strftime("%Y%m%d")
    seq = _atomic_increment(db, date_key)
    return f"{settings.SERIAL_PREFIX}-{date_key}-{seq:06d}"


def allocate_queue_sequence(db) -> int:
    """Allocates the next strictly-increasing, never-reused queue position."""
    return _atomic_increment(db, "QUEUE_SEQ")


def get_or_create_order_serial(db, order: Order) -> str:
    """
    Returns the order's print serial, generating and persisting one only
    if it doesn't already have one. Safe to call on every retry/reprint —
    idempotent by construction.
    """
    if order.print_serial:
        return order.print_serial

    order.print_serial = allocate_daily_sequence(db)
    db.add(order)
    db.commit()
    db.refresh(order)
    return order.print_serial
