"""File retention: delete customer documents once they are no longer needed.

* Finished orders (COMPLETED / CANCELLED) lose their upload, printable PDF and
  preview ``FILE_RETENTION_DAYS`` after their last update.
* Abandoned drafts (an upload that never became an order) are swept by age.
Order rows and history are kept; only the files go.
"""
import asyncio
import logging
import os
import re
import shutil
import time
from datetime import datetime, timedelta

from app.config import settings
from app.database import SessionLocal
from app.models.order import Order

logger = logging.getLogger("cleanup_service")

TERMINAL_STATES = ("COMPLETED", "CANCELLED")
ORDER_PREFIX = re.compile(r"^(PRN-\d+)")


def _remove(path: str) -> None:
    if not path:
        return
    try:
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        elif os.path.exists(path):
            os.remove(path)
    except OSError as e:
        logger.warning(f"Could not remove {path}: {e}")


def _order_files(order: Order) -> list[str]:
    paths = [order.stored_file_path]
    if order.printable_pdf_path:
        paths.append(os.path.dirname(order.printable_pdf_path))  # processed/<order id>/
    paths.append(os.path.join(settings.STORAGE_DIR, "previews", f"{order.id}_thumb.png"))
    return paths


def purge_expired_files(db, now: datetime | None = None) -> dict:
    """Delete files for finished orders and orphaned drafts older than the retention window."""
    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=settings.FILE_RETENTION_DAYS)
    purged_orders = 0

    for order in db.query(Order).filter(Order.current_state.in_(list(TERMINAL_STATES))).all():
        if order.files_purged_at or not order.updated_at or order.updated_at > cutoff:
            continue
        for path in _order_files(order):
            _remove(path)
        order.files_purged_at = now
        purged_orders += 1
    db.commit()

    # Orphan sweep: files whose PRN id never became an order.
    known = {o["id"] for o in db.database.orders.find({}, {"id": 1})}
    orphans = 0
    age_limit = time.time() - settings.FILE_RETENTION_DAYS * 86400
    for sub in ("uploads", "processed", "previews"):
        base = os.path.join(settings.STORAGE_DIR, sub)
        if not os.path.isdir(base):
            continue
        for name in os.listdir(base):
            match = ORDER_PREFIX.match(name)
            full = os.path.join(base, name)
            if match and match.group(1) not in known and os.path.getmtime(full) < age_limit:
                _remove(full)
                orphans += 1
    logger.info(f"Retention: purged files for {purged_orders} orders, removed {orphans} orphaned drafts")
    return {"orders": purged_orders, "orphans": orphans}


async def retention_loop(interval_hours: float = 6.0) -> None:
    """Background task started at app startup."""
    while True:
        try:
            db = SessionLocal()
            try:
                await asyncio.to_thread(purge_expired_files, db)
            finally:
                db.close()
        except Exception:
            logger.exception("Retention job failed")
        await asyncio.sleep(interval_hours * 3600)
