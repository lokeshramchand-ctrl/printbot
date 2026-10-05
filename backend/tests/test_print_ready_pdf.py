import zlib
import fitz

from app.config import settings
from app.models.customer import Customer
from app.models.order import Order
from app.services.pdf_stamp_service import prepare_print_ready_pdf
from app.services.print_service import print_service
from app.services.serial_service import PICKUP_ALPHABET, allocate_pickup_code, get_or_create_pickup_code

SERIAL = "PB-20261005-000042"


def _pdf(tmp_path, pages, name="doc.pdf"):
    p = str(tmp_path / name)
    doc = fitz.open()
    for i in range(pages):
        doc.new_page(width=595, height=842).insert_text((50, 50), f"content {i + 1}", fontsize=14)
    doc.save(p)
    doc.close()
    return p


def _texts(path):
    doc = fitz.open(path)
    out = [p.get_text() for p in doc]
    doc.close()
    return out


def _order(db, oid, pdf, pages, copies=1, sides="single"):
    c = Customer(whatsapp_number=f"+91{zlib.crc32(oid.encode()) % 10**10:010d}", display_name="T")
    db.add(c)
    db.commit()
    o = Order(id=oid, customer_id=c.id, printable_pdf_path=pdf, total_pages=pages, copies=copies,
              paper_size="A4", color_mode="BW", sides=sides, total_amount=5.0,
              payment_status="PAID", current_state="PAID")
    db.add(o)
    db.commit()
    return o


def test_single_sided_copies_are_expanded_and_labelled(tmp_path):
    path = _pdf(tmp_path, 3)
    assert prepare_print_ready_pdf(path, SERIAL, "T-1", copies=2, sides="single") == 2
    texts = _texts(path)
    assert len(texts) == 6
    assert "Copy 1/2" in texts[0] and "Pg 1/3" in texts[0]
    assert "Copy 2/2" in texts[3] and "Pg 1/3" in texts[3]
    assert all(SERIAL in t for t in texts)
    assert "Sheet" not in texts[0]


def test_duplex_labels_sheet_and_side_and_pads_odd_copies(tmp_path):
    path = _pdf(tmp_path, 3)
    prepare_print_ready_pdf(path, SERIAL, "T-1", copies=2, sides="double")
    texts = _texts(path)
    # copy 1: 3 pages + blank back, copy 2: 3 pages (last copy is not padded)
    assert len(texts) == 7
    assert "Sheet 1/2 F" in texts[0] and "Sheet 1/2 B" in texts[1] and "Sheet 2/2 F" in texts[2]
    assert "Blank back" in texts[3] and "Sheet 2/2 B" in texts[3]
    # copy 2 starts on a fresh sheet's front
    assert "Copy 2/2" in texts[4] and "Sheet 1/2 F" in texts[4]


def test_cover_sheet_has_pickup_code_and_keeps_content_on_fresh_sheet(tmp_path):
    path = _pdf(tmp_path, 2)
    prepare_print_ready_pdf(path, SERIAL, "T-1", sides="double", pickup_code="K7M2",
                            cover_lines=["Order PRN-1", "2 page(s)"])
    texts = _texts(path)
    assert "K7M2" in texts[0] and "PICKUP CODE" in texts[0]
    assert texts[1].strip() == ""          # blank back of the cover
    assert "content 1" in texts[2] and "Pg 1/2" in texts[2]   # content starts on a new sheet
    assert "Pg 1/2" not in texts[0]        # cover isn't a numbered page


def test_oversized_job_is_not_expanded(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MAX_EXPANDED_PAGES", 5)
    path = _pdf(tmp_path, 3)
    assert prepare_print_ready_pdf(path, SERIAL, "T-1", copies=4) == 1
    assert len(_texts(path)) == 3


def test_pickup_code_format_unique_and_idempotent(setup_db, tmp_path):
    db = setup_db
    codes = {allocate_pickup_code(db) for _ in range(50)}
    assert all(len(c) == 4 and set(c) <= set(PICKUP_ALPHABET) for c in codes)
    order = _order(db, "PRN-PK-1", _pdf(tmp_path, 1), 1)
    assert get_or_create_pickup_code(db, order) == get_or_create_pickup_code(db, order)


def test_submit_job_bakes_copies_once_and_retry_does_not_restamp(setup_db, tmp_path, monkeypatch):
    db = setup_db
    monkeypatch.setattr(settings, "COVER_SHEET_ENABLED", True)
    path = _pdf(tmp_path, 2)
    order = _order(db, "PRN-PK-2", path, 2, copies=3)
    print_service.submit_job(db, order)
    assert order.stamped_copies == 3 and order.pickup_code
    pages_after_first = len(_texts(path))
    assert pages_after_first == 1 + 3 * 2          # cover + 3 copies x 2 pages
    print_service.submit_job(db, order)            # retry
    assert len(_texts(path)) == pages_after_first


def test_cover_sheet_skipped_for_single_page_and_when_disabled(setup_db, tmp_path, monkeypatch):
    db = setup_db
    one = _order(db, "PRN-PK-3", _pdf(tmp_path, 1, "a.pdf"), 1)
    print_service.submit_job(db, one)
    assert len(_texts(one.printable_pdf_path)) == 1

    monkeypatch.setattr(settings, "COVER_SHEET_ENABLED", False)
    two = _order(db, "PRN-PK-4", _pdf(tmp_path, 2, "b.pdf"), 2)
    print_service.submit_job(db, two)
    assert len(_texts(two.printable_pdf_path)) == 2
