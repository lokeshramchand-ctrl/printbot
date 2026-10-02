import os
import logging
import threading
from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session
from app.config import settings
from app.models.printer import Printer
from app.models.print_job import PrintJob
from app.models.order import Order
from app.models.history import OrderStatusHistory
from app.services.serial_service import get_or_create_order_serial, allocate_queue_sequence
from app.services.pdf_stamp_service import stamp_printable_pdf, customer_label_for

logger = logging.getLogger("print_service")

# Serialises queue draining so two triggers (printer switched on + new payment)
# can never walk the same QUEUED jobs concurrently.
_dispatch_lock = threading.Lock()

# Try pycups import if Linux CUPS is installed
try:
    import cups
    HAS_PYCUPS = True
except ImportError:
    HAS_PYCUPS = False

AGENT_STALE_SECONDS = 90  # an agent printer not seen in a heartbeat for this long is unreachable


def printer_reachable(p: Printer) -> bool:
    """Local (CUPS) printers are always reachable; agent printers only while heartbeats arrive."""
    if not p.agent_id:
        return True
    return bool(p.last_seen_at) and (datetime.utcnow() - p.last_seen_at).total_seconds() <= AGENT_STALE_SECONDS


class PrintService:
    """PrintQueue & CUPS Printer Subsystem Abstraction."""

    @classmethod
    def sync_printers(cls, db: Session) -> List[Printer]:
        """Discover and sync physical CUPS printers into database."""
        if HAS_PYCUPS and not settings.USE_VIRTUAL_PRINTER:
            try:
                conn = cups.Connection(host=settings.CUPS_HOST, port=settings.CUPS_PORT)
                cups_printers = conn.getPrinters()
                
                for p_name, p_info in cups_printers.items():
                    existing = db.query(Printer).filter(Printer.cups_name == p_name).first()
                    is_accepting = p_info.get("printer-is-accepting-jobs", True)
                    state = p_info.get("printer-state", 3) # 3=idle, 4=printing, 5=stopped
                    
                    status_str = "ONLINE" if state == 3 else ("BUSY" if state == 4 else "OFFLINE")
                    
                    if existing:
                        # CUPS may switch a printer off, but only an admin switches it back on.
                        if not is_accepting:
                            existing.is_online = False
                        existing.status = status_str if existing.is_online else "OFFLINE"
                    else:
                        new_p = Printer(
                            name=p_name.replace("_", " ").title(),
                            cups_name=p_name,
                            model=p_info.get("printer-make-and-model", "CUPS Printer"),
                            location=p_info.get("printer-location", "Print Shop"),
                            is_online=is_accepting,
                            status=status_str
                        )
                        db.add(new_p)
                db.commit()
            except Exception as e:
                logger.error(f"CUPS printer sync error: {str(e)}")

        # Ensure default virtual printer exists in DB if empty
        if db.query(Printer).count() == 0:
            default_p = Printer(
                name="Main Express LaserJet",
                cups_name="express_laserjet_v1",
                model="HP LaserJet Enterprise M608 (Virtual)",
                location="Counter #1",
                status="ONLINE",
                is_online=True,
                is_default=True,
                is_color_supported=True,
                supported_paper_sizes="A4,A3,Letter"
            )
            db.add(default_p)
            db.commit()

        return db.query(Printer).all()

    @classmethod
    def pick_printer(cls, db: Session, color_mode: Optional[str], paper_size: Optional[str],
                     preferred_id: Optional[int] = None) -> Optional[Printer]:
        """Choose an online printer able to handle the job, or None.

        An online printer is the only candidate; if several are on, the preferred
        one (admin's explicit choice) wins, otherwise the least-used one, so work
        is spread across all active printers.
        """
        candidates = []
        for p in db.query(Printer).all():
            if not p.is_online or not printer_reachable(p):
                continue
            if (color_mode or "").upper() == "COLOR" and not p.is_color_supported:
                continue
            sizes = {x.strip().upper() for x in (p.supported_paper_sizes or "").split(",") if x.strip()}
            if paper_size and sizes and paper_size.upper() not in sizes:
                continue
            candidates.append(p)
        if not candidates:
            return None
        for p in candidates:
            if preferred_id and p.id == preferred_id:
                return p
        candidates.sort(key=lambda p: (p.status == "BUSY", p.total_printed_jobs or 0, not p.is_default, p.id))
        return candidates[0]

    @classmethod
    def dispatch_queue(cls, db: Session) -> List[str]:
        """Print every QUEUED job (oldest first) that now has an online printer.

        Called when a printer is switched on/added. Returns order ids that printed.
        """
        printed: List[str] = []
        with _dispatch_lock:
            jobs = db.query(PrintJob).filter(PrintJob.status == "QUEUED").all()
            jobs.sort(key=lambda j: (j.queue_sequence or 0, j.id))
            for job in jobs:
                if cls.execute_print_job(db, job.id):
                    printed.append(job.order_id)
        return printed

    @classmethod
    def submit_job(cls, db: Session, order: Order, target_printer_id: Optional[int] = None) -> PrintJob:
        """
        Submits an order to the print queue.

        Also guarantees the order has a print serial and that its printable
        PDF has been stamped with it — both steps are idempotent, so
        calling submit_job again for a retry/reprint of the same order
        never mints a second serial or double-stamps the file.
        """
        # Find an online printer; if none is on, the job simply waits in the queue
        # (printer_id stays empty) until dispatch_queue() finds one.
        printer = cls.pick_printer(db, order.color_mode, order.paper_size, target_printer_id)

        # --- Serial numbering: order-level, idempotent (see serial_service) ---
        serial = get_or_create_order_serial(db, order)

        if not order.serial_stamped_at and order.printable_pdf_path and os.path.exists(order.printable_pdf_path):
            customer_label = customer_label_for(order.customer)
            stamped = stamp_printable_pdf(order.printable_pdf_path, serial, customer_label, when=order.created_at)
            if stamped:
                order.serial_stamped_at = datetime.utcnow()
                db.add(order)
                db.commit()
            else:
                logger.error(f"Serial stamping failed for order {order.id}; proceeding without a stamped PDF.")

        # --- Queue sequence: global, monotonic, never reused (see serial_service) ---
        queue_sequence = allocate_queue_sequence(db)

        # Create PrintJob record
        print_job = PrintJob(
            order_id=order.id,
            printer_id=printer.id if printer else None,
            status="QUEUED",
            copies=order.copies,
            paper_size=order.paper_size,
            color_mode=order.color_mode,
            sides=order.sides,
            total_pages=order.total_pages,
            print_serial=serial,
            queue_sequence=queue_sequence,
        )
        db.add(print_job)

        # Update order state
        previous_state = order.current_state
        order.current_state = "QUEUED"
        order.print_status = "QUEUED"
        if printer:
            order.printer_id = printer.id

        history = OrderStatusHistory(
            order_id=order.id,
            from_status=previous_state,
            to_status="QUEUED",
            trigger_source="SYSTEM",
            notes=(f"Order added to print queue (serial {serial}, position #{queue_sequence}) for printer {printer.name}"
                   if printer else
                   f"Order queued (serial {serial}, position #{queue_sequence}); waiting for a printer to be turned on")
        )
        db.add(history)
        db.commit()
        db.refresh(print_job)

        return print_job

    @classmethod
    def execute_print_job(cls, db: Session, job_id: int) -> bool:
        """Executes a queued print job via CUPS or Virtual Driver."""
        job = db.query(PrintJob).filter(PrintJob.id == job_id).first()
        # Guard against double-printing: only a QUEUED job may be executed.
        # This blocks accidental re-execution of a job that already
        # completed, is currently printing, or was cancelled — e.g. from a
        # double-clicked "force print" or two workers racing on the same job.
        if not job or job.status != "QUEUED":
            return False

        order = db.query(Order).filter(Order.id == job.order_id).first()
        if order and order.current_state in ("CANCELLED", "REFUNDED"):
            job.status = "CANCELLED"
            db.commit()
            return False

        printer = db.query(Printer).filter(Printer.id == job.printer_id).first() if job.printer_id else None
        if printer and printer.agent_id and printer.is_online and printer_reachable(printer):
            return False  # stays QUEUED: the paired agent claims it (see agent_service.claim_next_job)
        if db.query(Printer).count() > 0 and (not printer or not printer.is_online or not printer_reachable(printer)):
            # Assigned printer is off (or none yet): move to any online printer, else keep waiting.
            printer = cls.pick_printer(db, job.color_mode, job.paper_size)
            if not printer:
                job.printer_id = None
                db.commit()
                return False
            job.printer_id = printer.id
            if order:
                order.printer_id = printer.id
            db.commit()
            if printer.agent_id:
                return False  # re-assigned to an agent printer; the agent will claim it

        if not order or not order.printable_pdf_path or not os.path.exists(order.printable_pdf_path):
            job.status = "FAILED"
            job.error_message = "Printable PDF file missing or inaccessible."
            if order:
                order.current_state = "PRINT_FAILED"
                order.print_status = "FAILED"
            if printer:
                printer.current_job_id = None
                printer.status = "ONLINE"
            db.commit()
            return False

        # Mark PRINTING
        job.status = "PRINTING"
        job.started_at = datetime.utcnow()
        order.current_state = "PRINTING"
        order.print_status = "PRINTING"
        if printer:
            printer.status = "BUSY"
            printer.current_job_id = order.id
        db.commit()

        pdf_path = order.printable_pdf_path
        options = {
            "copies": str(job.copies),
            "media": job.paper_size,
            "ColorModel": "Color" if job.color_mode.upper() == "COLOR" else "Gray",
            "sides": "two-sided-long-edge" if job.sides.lower() == "double" else "one-sided"
        }

        success = False
        cups_job_num = None

        # Execute via CUPS if available
        if HAS_PYCUPS and printer and not settings.USE_VIRTUAL_PRINTER:
            try:
                conn = cups.Connection(host=settings.CUPS_HOST, port=settings.CUPS_PORT)
                cups_job_num = conn.printFile(printer.cups_name, pdf_path, f"PrintBot Order {order.id}", options)
                job.cups_job_id = cups_job_num
                success = True
            except Exception as e:
                logger.error(f"CUPS print file execution failed: {str(e)}")
                job.error_message = str(e)
                success = False
        else:
            # Simulated Virtual Printer Execution
            logger.info(f"[VIRTUAL PRINTER] Simulating print for Order #{order.id} on '{printer.name if printer else 'Virtual'}'")
            success = True

        if success:
            job.status = "COMPLETED"
            job.completed_at = datetime.utcnow()
            order.current_state = "COMPLETED"
            order.print_status = "COMPLETED"
            if printer:
                printer.status = "ONLINE"
                printer.current_job_id = None
                printer.total_printed_jobs += 1
            
            history = OrderStatusHistory(
                order_id=order.id,
                from_status="PRINTING",
                to_status="COMPLETED",
                trigger_source="PRINTER",
                notes=f"Document printed successfully (serial {job.print_serial})."
            )
            db.add(history)
            db.commit()
            return True
        else:
            job.status = "FAILED"
            job.retry_count = (job.retry_count or 0) + 1
            order.current_state = "PRINT_FAILED"
            order.print_status = "FAILED"
            if printer:
                printer.status = "ERROR"
                printer.current_job_id = None
            db.commit()
            return False

print_service = PrintService()
