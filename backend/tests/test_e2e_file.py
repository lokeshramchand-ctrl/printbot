"""End-to-end: every document in TESTDATA_DIR goes through the whole bot flow and prints.

Drop PDF/DOC/DOCX/JPG/PNG files into ``testdata/`` (mounted at /testdata in docker). With none
present a generated 3-page PDF is used so the suite still exercises the pipeline.
"""
import os
import shutil
from pathlib import Path

import fitz
import pytest

from app.config import settings
from app.models.order import Order
from app.models.payment import Payment
from app.models.print_job import PrintJob
from app.services.telegram_service import telegram_service
from test_bot_flow import FakeTelegram, customer, say

SUPPORTED = {".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png"}
DIRS = [os.environ.get("TESTDATA_DIR", ""), "/testdata", str(Path(__file__).resolve().parents[2] / "testdata")]


def _files():
    for d in DIRS:
        if d and Path(d).is_dir():
            found = sorted(p for p in Path(d).iterdir() if p.suffix.lower() in SUPPORTED)
            if found:
                return found
    return []


FILES = _files() or [None]


@pytest.mark.parametrize("source", FILES, ids=lambda p: p.name if p else "generated-sample.pdf")
async def test_document_flows_through_bot_payment_and_print(setup_db, monkeypatch, tmp_path, source):
    db = setup_db
    fake = FakeTelegram()
    monkeypatch.setattr(telegram_service, "_post_request", fake.post)
    monkeypatch.setattr(settings, "STORAGE_DIR", str(tmp_path))
    for sub in ("uploads", "processed", "previews"):
        (tmp_path / sub).mkdir()

    if source is None:
        source = tmp_path / "generated-sample.pdf"
        doc = fitz.open()
        for i in range(3):
            doc.new_page().insert_text((50, 50), f"page {i + 1}")
        doc.save(str(source))
        doc.close()

    async def download(file_id, save_path):
        shutil.copyfile(source, save_path)
        return True

    monkeypatch.setattr(telegram_service, "download_incoming_file", download)

    await say(db, "/start")
    await say(db, document=source.name)
    assert customer(db).bot_state == "ASK_COPIES", fake.texts()[-1]
    for button in ("COPIES_1", "COLOR_BW", "PAPER_A4", "PAGES_ALL", "SIDES_SINGLE"):
        await say(db, button=button)

    order = db.query(Order).first()
    assert order and order.current_state == "PAYMENT_PENDING" and order.total_pages >= 1
    assert order.total_amount > 0
    pay = [b for b in fake.last_buttons() if b.get("callback_data", "").startswith("DEMO_PAY_")]
    assert pay, "demo pay button missing"
    await say(db, button=pay[0]["callback_data"])

    order = db.query(Order).filter(Order.id == order.id).first()
    assert order.payment_status == "PAID" and order.current_state == "COMPLETED", order.failure_reason
    assert order.print_serial and order.serial_stamped_at
    assert os.path.exists(order.printable_pdf_path)
    with fitz.open(order.printable_pdf_path) as pdf:
        assert pdf.page_count == order.total_pages
        assert order.print_serial in pdf[0].get_text(), "serial stamp missing on printed page"
    assert db.query(Payment).filter(Payment.order_id == order.id).first().status == "CAPTURED"
    assert db.query(PrintJob).filter(PrintJob.order_id == order.id).first().status == "COMPLETED"
    print(f"\nE2E ok: {source.name} -> {order.id} {order.print_serial} pages={order.total_pages} Rs{order.total_amount}")
