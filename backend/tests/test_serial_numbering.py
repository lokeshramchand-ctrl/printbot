import os
import threading
import fitz
import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.database import Base
from app.services.pricing_service import pricing_service
from app.services.print_service import print_service
from app.services.serial_service import (
    get_or_create_order_serial,
    allocate_daily_sequence,
    allocate_queue_sequence,
)
from app.services.pdf_stamp_service import stamp_printable_pdf
from app.models.customer import Customer
from app.models.order import Order
from app.models.print_job import PrintJob

TEST_DATABASE_URL = "sqlite:///./test_serial.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False}, poolclass=NullPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    pricing_service.seed_defaults_if_empty(db)
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    if os.path.exists("./test_serial.db"):
        try:
            os.remove("./test_serial.db")
        except Exception:
            pass


def _make_order(db, order_id: str, pdf_path: str, customer_id: int = None) -> Order:
    if customer_id is None:
        customer = Customer(whatsapp_number="+919876500000", display_name="Serial Test User")
        db.add(customer)
        db.commit()
        customer_id = customer.id

    order = Order(
        id=order_id,
        customer_id=customer_id,
        original_file_name="doc.pdf",
        printable_pdf_path=pdf_path,
        total_pages=1,
        copies=1,
        paper_size="A4",
        color_mode="BW",
        sides="single",
        total_amount=5.0,
        payment_status="PAID",
        current_state="PAID",
    )
    db.add(order)
    db.commit()
    return order


def _make_pdf(tmp_path, name="doc.pdf", pages=1):
    p = str(tmp_path / name)
    doc = fitz.open()
    for _ in range(pages):
        pg = doc.new_page(width=595, height=842)
        pg.insert_text((50, 50), "Customer's original content", fontsize=14)
    doc.save(p)
    doc.close()
    return p


# ---------------------------------------------------------------------------
# Uniqueness under concurrency
# ---------------------------------------------------------------------------

def test_daily_sequence_unique_under_concurrent_threads(setup_db):
    """
    Simulates many concurrent allocations (e.g. multiple orders entering
    the queue at once, or multiple worker threads) and asserts every
    allocated serial is distinct — the atomic UPDATE in serial_service
    must serialize allocations even though threads race to call it.
    """
    results = []
    lock = threading.Lock()
    errors = []

    def worker():
        try:
            # Each thread needs its own session/connection, matching how
            # a real request-scoped db session would work.
            thread_db = TestingSessionLocal()
            serial = allocate_daily_sequence(thread_db)
            with lock:
                results.append(serial)
            thread_db.close()
        except Exception as e:
            with lock:
                errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(25)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Unexpected errors during concurrent allocation: {errors}"
    assert len(results) == 25
    assert len(set(results)) == 25, "Duplicate serial allocated under concurrency"


def test_queue_sequence_unique_and_monotonic_under_concurrency(setup_db):
    """Same guarantee, for the queue-position counter used for FIFO ordering."""
    results = []
    lock = threading.Lock()

    def worker():
        thread_db = TestingSessionLocal()
        seq = allocate_queue_sequence(thread_db)
        with lock:
            results.append(seq)
        thread_db.close()

    threads = [threading.Thread(target=worker) for _ in range(30)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(set(results)) == 30, "Duplicate queue sequence allocated under concurrency"
    assert sorted(results) == list(range(1, 31)), "Queue sequence is not a gapless increasing run"


# ---------------------------------------------------------------------------
# Idempotency across retries / reprints
# ---------------------------------------------------------------------------

def test_order_serial_generated_once_and_reused_on_retry(setup_db, tmp_path):
    """Calling get_or_create_order_serial repeatedly must never change the value."""
    db = setup_db
    pdf_path = _make_pdf(tmp_path)
    order = _make_order(db, "PRN-SER-001", pdf_path)

    first = get_or_create_order_serial(db, order)
    second = get_or_create_order_serial(db, order)
    third = get_or_create_order_serial(db, order)

    assert first == second == third
    assert order.print_serial == first


def test_submit_job_retry_reuses_serial_and_does_not_double_stamp(setup_db, tmp_path):
    """
    Simulates a failed print being retried by an admin: submit_job is
    called twice for the same order (as orders.py does for PRINT/RETRY).
    The serial must stay identical, and the PDF must not accumulate a
    second stamp on top of the first.
    """
    db = setup_db
    pdf_path = _make_pdf(tmp_path)
    order = _make_order(db, "PRN-SER-002", pdf_path)

    job1 = print_service.submit_job(db, order)
    serial_after_first_submit = order.print_serial
    stamped_at_first = order.serial_stamped_at
    assert serial_after_first_submit is not None
    assert stamped_at_first is not None

    # A distinct PrintJob row is created for the retry (so the job history
    # is auditable), but the order-level serial and stamp must be reused.
    job2 = print_service.submit_job(db, order)

    assert job1.id != job2.id
    assert order.print_serial == serial_after_first_submit
    assert order.serial_stamped_at == stamped_at_first, "Reprint re-stamped the PDF instead of reusing the existing stamp"
    assert job1.print_serial == job2.print_serial == serial_after_first_submit

    # Confirm the file actually contains exactly one stamp line, not two.
    doc = fitz.open(pdf_path)
    text = doc[0].get_text()
    doc.close()
    assert text.count(serial_after_first_submit) == 1, "PDF was stamped more than once"


def test_execute_print_job_rejects_double_execution(setup_db, tmp_path):
    """A job that is already COMPLETED (or otherwise not QUEUED) must not be re-executed."""
    db = setup_db
    pdf_path = _make_pdf(tmp_path)
    order = _make_order(db, "PRN-SER-003", pdf_path)

    job = print_service.submit_job(db, order)
    first_result = print_service.execute_print_job(db, job.id)
    assert first_result is True
    assert order.current_state == "COMPLETED"

    # Re-running against the same (now COMPLETED) job must be a no-op that
    # returns False, guarding against double-printing.
    second_result = print_service.execute_print_job(db, job.id)
    assert second_result is False


# ---------------------------------------------------------------------------
# PDF stamping correctness
# ---------------------------------------------------------------------------

def test_stamp_preserves_original_content_and_page_geometry(tmp_path):
    pdf_path = _make_pdf(tmp_path, pages=3)

    doc_before = fitz.open(pdf_path)
    original_texts = [p.get_text() for p in doc_before]
    original_rects = [p.rect for p in doc_before]
    doc_before.close()

    ok = stamp_printable_pdf(pdf_path, "PB-20260906-000042", "W-9")
    assert ok is True

    doc_after = fitz.open(pdf_path)
    assert len(doc_after) == 3
    for i, page in enumerate(doc_after):
        assert page.rect == original_rects[i], "Stamping must never change page dimensions"
        text = page.get_text()
        assert original_texts[i].strip() in text, "Original customer content was altered or removed"
        assert "PB-20260906-000042" in text
        assert f"Pg {i + 1}/3" in text
    doc_after.close()


def test_stamp_is_per_page_with_correct_page_numbers(tmp_path):
    pdf_path = _make_pdf(tmp_path, pages=5)
    stamp_printable_pdf(pdf_path, "PB-20260906-000099", "T-3")

    doc = fitz.open(pdf_path)
    for i, page in enumerate(doc, start=1):
        text = page.get_text()
        assert f"Pg {i}/5" in text
    doc.close()


def test_original_uploaded_file_is_never_touched_by_stamping(tmp_path):
    """
    The stamp must only ever be applied to the generated printable copy —
    never to the customer's original upload.
    """
    original_path = str(tmp_path / "customers_original.pdf")
    doc = fitz.open()
    doc.new_page().insert_text((50, 50), "original upload, untouched")
    doc.save(original_path)
    doc.close()
    original_bytes = open(original_path, "rb").read()

    printable_path = str(tmp_path / "printable.pdf")
    doc2 = fitz.open()
    doc2.new_page().insert_text((50, 50), "original upload, untouched")
    doc2.save(printable_path)
    doc2.close()

    stamp_printable_pdf(printable_path, "PB-20260906-000001", "W-1")

    # The original file (a separate path, as document_service always keeps
    # stored_file_path and printable_pdf_path distinct) is byte-for-byte
    # unchanged.
    assert open(original_path, "rb").read() == original_bytes


# ---------------------------------------------------------------------------
# Queue ordering
# ---------------------------------------------------------------------------

def test_queue_sequence_assigned_in_submission_order(setup_db, tmp_path):
    db = setup_db
    orders = []
    for i in range(4):
        pdf_path = _make_pdf(tmp_path, name=f"doc{i}.pdf")
        order = _make_order(db, f"PRN-SER-Q{i}", pdf_path)
        orders.append(order)

    jobs = [print_service.submit_job(db, o) for o in orders]
    sequences = [j.queue_sequence for j in jobs]

    assert sequences == sorted(sequences), "Queue sequence must increase in submission order"
    assert len(set(sequences)) == len(sequences)
