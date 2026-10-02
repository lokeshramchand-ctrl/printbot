"""End-to-end bot conversations against in-memory Mongo with a fake Telegram."""
import itertools
import shutil

import fitz
import pytest

from app.config import settings
from app.models.customer import Customer
from app.models.order import Order
from app.models.payment import Payment
from app.services.bot_state_machine import (
    bot_state_machine, parse_color, parse_copies, parse_pages_choice, parse_paper, parse_sides,
)
from app.services.telegram_service import telegram_service
from app.utils.page_ranges import PageRangeError, parse_page_range

CHAT = "555"
_update_ids = itertools.count(1)


class FakeTelegram:
    def __init__(self):
        self.sent = []

    async def post(self, endpoint, payload):
        self.sent.append((endpoint, payload))
        return {"ok": True}

    def texts(self):
        return [p.get("text", "") for e, p in self.sent if e == "sendMessage"]

    def last_buttons(self):
        for endpoint, payload in reversed(self.sent):
            if endpoint == "sendMessage" and payload.get("reply_markup"):
                return [b for row in payload["reply_markup"]["inline_keyboard"] for b in row]
        return []


@pytest.fixture
def tg(monkeypatch, tmp_path):
    fake = FakeTelegram()
    monkeypatch.setattr(telegram_service, "_post_request", fake.post)
    monkeypatch.setattr(settings, "STORAGE_DIR", str(tmp_path))
    for sub in ("uploads", "processed", "previews"):
        (tmp_path / sub).mkdir()

    sample = tmp_path / "sample.pdf"
    doc = fitz.open()
    for i in range(10):
        doc.new_page().insert_text((50, 50), f"page {i + 1}")
    doc.save(str(sample))
    doc.close()

    async def fake_download(file_id, save_path):
        shutil.copyfile(sample, save_path)
        return True

    monkeypatch.setattr(telegram_service, "download_incoming_file", fake_download)
    return fake


async def say(db, text=None, *, button=None, document=None, chat=CHAT):
    update = {"update_id": next(_update_ids)}
    if button:
        update["callback_query"] = {"id": "cb", "data": button, "from": {"first_name": "Asha"},
                                    "message": {"chat": {"id": int(chat)}}}
    else:
        message = {"chat": {"id": int(chat)}, "from": {"first_name": "Asha"}}
        if document:
            message["document"] = {"file_id": "f1", "file_name": document}
        else:
            message["text"] = text
        update["message"] = message
    await bot_state_machine.handle_telegram_update(db, update)


async def upto_sides(db, pages=None):
    await say(db, "/start")
    await say(db, document="my_file_v1*.pdf")
    await say(db, button="COPIES_2")
    await say(db, button="COLOR_BW")
    await say(db, button="PAPER_A4")
    if pages:
        await say(db, button="PAGES_SPECIFIC")
        await say(db, pages)
    else:
        await say(db, button="PAGES_ALL")


def customer(db, chat=CHAT):
    return db.query(Customer).filter(Customer.telegram_chat_id == chat).first()


# ---------------- parsers ----------------

def test_parsers_are_strict():
    assert parse_copies("12") == 12 and parse_copies("COPIES_3") == 3 and parse_copies("5 copies") == 5
    assert parse_copies("abc") is None and parse_copies("1 2") is None
    assert parse_color("COLOR_COLOR") == "Color" and parse_color("B&W") == "BW" and parse_color("maybe") is None
    assert parse_paper("PAPER_LETTER") == "Letter" and parse_paper("a4") == "A4" and parse_paper("foolscap") is None
    assert parse_sides("SIDES_DOUBLE") == "double" and parse_sides("2") == "double" and parse_sides("x") is None
    assert parse_pages_choice("PAGES_SPECIFIC") == "SPECIFIC" and parse_pages_choice("blah") is None


def test_page_range_parsing():
    assert parse_page_range("3, 1-2, 2", 10) == ("1-3", [1, 2, 3])
    assert parse_page_range("1-3,5,8-10", 10)[0] == "1-3,5,8-10"
    for bad in ("0", "5-3", "11", "a-b", "1--2", ""):
        with pytest.raises(PageRangeError):
            parse_page_range(bad, 10)


# ---------------- flows ----------------

async def test_typed_copies_12_is_12_not_1(setup_db, tg):
    db = setup_db
    await say(db, "/start")
    await say(db, document="a.pdf")
    await say(db, "12")
    assert customer(db).state_data["copies"] == 12 and customer(db).bot_state == "ASK_COLOR"


async def test_invalid_input_reprompts_instead_of_defaulting(setup_db, tg):
    db = setup_db
    await say(db, "/start")
    await say(db, document="a.pdf")
    await say(db, "banana")
    assert customer(db).bot_state == "ASK_COPIES"
    await say(db, "500")
    assert customer(db).bot_state == "ASK_COPIES"
    assert any("between 1 and" in t for t in tg.texts())


async def test_demo_payment_full_pipeline(setup_db, tg):
    db = setup_db
    await upto_sides(db)
    await say(db, button="SIDES_DOUBLE")

    order = db.query(Order).first()
    assert order.current_state == "PAYMENT_PENDING" and order.copies == 2 and order.sides == "double"
    assert customer(db).bot_state == "WAITING_FOR_PAYMENT"
    pay = [b for b in tg.last_buttons() if b.get("callback_data", "").startswith("DEMO_PAY_")]
    assert pay and "Demo" in pay[0]["text"]
    assert any("file\\_v1\\*" in t for t in tg.texts()), "filename must be Markdown-escaped"

    await say(db, button=pay[0]["callback_data"])
    order = db.query(Order).filter(Order.id == order.id).first()
    assert order.payment_status == "PAID" and order.current_state == "COMPLETED"
    assert order.print_serial and order.serial_stamped_at
    assert db.query(Payment).filter(Payment.order_id == order.id).first().status == "CAPTURED"
    assert customer(db).bot_state == "IDLE" and customer(db).active_order_id is None
    assert any("Print complete" in t for t in tg.texts())
    assert any(e == "answerCallbackQuery" for e, _ in tg.sent), "buttons must be acknowledged"


async def test_double_tap_pay_prints_once(setup_db, tg):
    db = setup_db
    await upto_sides(db)
    await say(db, button="SIDES_SINGLE")
    order_id = db.query(Order).first().id
    await say(db, button=f"DEMO_PAY_{order_id}")
    await say(db, button=f"DEMO_PAY_{order_id}")
    assert db.database.print_jobs.count_documents({"order_id": order_id}) == 1
    assert db.database.payments.count_documents({"order_id": order_id, "status": "CAPTURED"}) == 1


async def test_cannot_pay_another_customers_order(setup_db, tg):
    db = setup_db
    await upto_sides(db)
    await say(db, button="SIDES_SINGLE")
    order_id = db.query(Order).first().id
    await say(db, button=f"DEMO_PAY_{order_id}", chat="999")
    assert db.query(Order).filter(Order.id == order_id).first().payment_status == "PENDING"


async def test_specific_pages_trim_pdf_and_price(setup_db, tg):
    db = setup_db
    await upto_sides(db, pages="1-3, 5")
    await say(db, button="SIDES_SINGLE")
    order = db.query(Order).first()
    assert order.pages_to_print == "1-3,5" and order.total_pages == 4
    printed = fitz.open(order.printable_pdf_path)
    assert len(printed) == 4 and "page 5" in printed[3].get_text()
    printed.close()
    # A4 B&W single = Rs 2/page * 4 pages * 2 copies = Rs 16
    assert order.total_amount == 16.0


async def test_bad_page_range_is_rejected_then_recovers(setup_db, tg):
    db = setup_db
    await upto_sides(db, pages="99")
    assert customer(db).bot_state == "ASK_PAGE_RANGE"
    assert any("only has 10 page" in t for t in tg.texts())
    await say(db, "2-4")
    assert customer(db).bot_state == "ASK_SIDES"


async def test_cancel_cancels_the_order(setup_db, tg):
    db = setup_db
    await upto_sides(db)
    await say(db, button="SIDES_SINGLE")
    order_id = db.query(Order).first().id
    await say(db, button="CANCEL_ORDER")
    assert db.query(Order).filter(Order.id == order_id).first().current_state == "CANCELLED"
    assert customer(db).bot_state == "IDLE"
    await say(db, button=f"DEMO_PAY_{order_id}")  # stale button must not resurrect it
    assert db.query(Order).filter(Order.id == order_id).first().payment_status == "PENDING"


async def test_duplicate_update_is_ignored(setup_db, tg):
    db = setup_db
    update = {"update_id": 424242, "message": {"chat": {"id": 7}, "from": {"first_name": "A"}, "text": "/start"}}
    await bot_state_machine.handle_telegram_update(db, update)
    count = len(tg.sent)
    await bot_state_machine.handle_telegram_update(db, update)
    assert len(tg.sent) == count


async def test_waiting_for_payment_never_dead_ends(setup_db, tg):
    db = setup_db
    await upto_sides(db)
    await say(db, button="SIDES_SINGLE")
    await say(db, "hello?")
    assert any(b.get("callback_data", "").startswith("DEMO_PAY_") for b in tg.last_buttons())


async def test_production_mode_refuses_demo_pay(setup_db, tg, monkeypatch):
    db = setup_db
    await upto_sides(db)
    await say(db, button="SIDES_SINGLE")
    order_id = db.query(Order).first().id
    monkeypatch.setattr(settings, "PAYMENT_MODE", "razorpay")
    await say(db, button=f"DEMO_PAY_{order_id}")
    assert db.query(Order).filter(Order.id == order_id).first().payment_status == "PENDING"
