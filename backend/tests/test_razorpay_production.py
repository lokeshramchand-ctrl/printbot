"""Production Razorpay path: payment links, signed webhooks, hardening."""
import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from app.config import settings, validate_settings
from app.main import app
from app.models.customer import Customer
from app.models.order import Order
from app.services import payment_service
from app.services.razorpay_service import razorpay_service
from test_bot_flow import FakeTelegram, say, upto_sides, customer, tg  # noqa: F401  (fixtures)

WEBHOOK_SECRET = "whsec_test_123"


class FakePaymentLinks:
    def __init__(self):
        self.created, self.cancelled = [], []
        self.fail = False

    def create(self, payload):
        if self.fail:
            raise RuntimeError("gateway down")
        self.created.append(payload)
        n = len(self.created)
        return {"id": f"plink_{n}", "short_url": f"https://rzp.io/i/abc{n}", "expire_by": payload["expire_by"]}

    def cancel(self, link_id):
        self.cancelled.append(link_id)
        return {"id": link_id, "status": "cancelled"}


class FakeClient:
    def __init__(self):
        self.payment_link = FakePaymentLinks()


@pytest.fixture
def rzp(monkeypatch):
    monkeypatch.setattr(settings, "PAYMENT_MODE", "razorpay")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_test_AbCdEf123456")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "secretsecretsecret")
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", WEBHOOK_SECRET)
    client = FakeClient()
    monkeypatch.setattr(razorpay_service, "_client", client)
    return client


def signed_post(client, payload, secret=WEBHOOK_SECRET, event_id="evt_1", signature=True):
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json", "X-Razorpay-Event-Id": event_id}
    if signature:
        headers["X-Razorpay-Signature"] = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post("/webhooks/razorpay", content=body, headers=headers)


def paid_payload(order, link_id, amount=None, payment_id="pay_1"):
    amount = int(round(order.total_amount * 100)) if amount is None else amount
    return {
        "event": "payment_link.paid",
        "payload": {
            "payment_link": {"entity": {"id": link_id, "reference_id": order.id, "amount": amount}},
            "payment": {"entity": {"id": payment_id, "amount": amount, "currency": "INR", "method": "upi",
                                   "order_id": "order_rzp_1", "notes": {"order_id": order.id}}},
        },
    }


async def order_awaiting_payment(db):
    await upto_sides(db)
    await say(db, button="SIDES_SINGLE")
    return db.query(Order).first()


async def test_bot_sends_real_payment_link(setup_db, tg, rzp):
    db = setup_db
    order = await order_awaiting_payment(db)
    buttons = tg.last_buttons()
    assert buttons[0]["url"] == "https://rzp.io/i/abc1"
    assert not any(b.get("callback_data", "").startswith("DEMO_PAY_") for b in buttons)
    created = rzp.payment_link.created[0]
    assert created["amount"] == int(round(order.total_amount * 100)) and created["reference_id"] == order.id
    assert "customer" not in created, "a Telegram chat id is not a phone number"
    assert created["expire_by"] > 0


async def test_signed_webhook_marks_paid_and_prints_once(setup_db, tg, rzp):
    db = setup_db
    order = await order_awaiting_payment(db)
    client = TestClient(app)
    payload = paid_payload(order, "plink_1")

    assert signed_post(client, payload).json()["result"] == "paid"
    fresh = db.query(Order).filter(Order.id == order.id).first()
    assert fresh.payment_status == "PAID" and fresh.current_state == "COMPLETED"
    assert any("Print complete" in t for t in tg.texts()), "Telegram customer must be notified on Telegram"

    # Razorpay retries: same event id, and a different event id for the same payment.
    assert signed_post(client, payload).json()["status"] == "already_processed"
    assert signed_post(client, payload, event_id="evt_2").json()["result"] == "already_processed"
    assert db.database.print_jobs.count_documents({"order_id": order.id}) == 1


async def test_unsigned_or_forged_webhook_is_rejected(setup_db, tg, rzp):
    db = setup_db
    order = await order_awaiting_payment(db)
    client = TestClient(app)
    payload = paid_payload(order, "plink_1")
    assert signed_post(client, payload, signature=False).status_code == 400
    assert signed_post(client, payload, secret="wrong").status_code == 400
    assert db.query(Order).filter(Order.id == order.id).first().payment_status == "PENDING"


async def test_underpayment_does_not_release_print(setup_db, tg, rzp):
    db = setup_db
    order = await order_awaiting_payment(db)
    client = TestClient(app)
    res = signed_post(client, paid_payload(order, "plink_1", amount=100))
    assert res.json()["result"] == "amount_mismatch"
    assert db.query(Order).filter(Order.id == order.id).first().payment_status == "PENDING"


async def test_payment_link_of_another_order_is_rejected(setup_db, tg, rzp):
    db = setup_db
    order = await order_awaiting_payment(db)
    client = TestClient(app)
    res = signed_post(client, paid_payload(order, "plink_OTHER"))
    assert res.json()["result"] == "link_mismatch"
    assert db.query(Order).filter(Order.id == order.id).first().payment_status == "PENDING"


async def test_cancel_cancels_razorpay_link(setup_db, tg, rzp):
    db = setup_db
    await order_awaiting_payment(db)
    await say(db, button="CANCEL_ORDER")
    assert rzp.payment_link.cancelled == ["plink_1"]


async def test_paid_after_cancel_flags_refund(setup_db, tg, rzp):
    db = setup_db
    order = await order_awaiting_payment(db)
    await say(db, button="CANCEL_ORDER")
    res = signed_post(TestClient(app), paid_payload(order, "plink_1"))
    assert res.json()["result"] == "paid_after_cancel"
    assert db.query(Order).filter(Order.id == order.id).first().current_state == "CANCELLED"
    assert db.database.order_status_history.count_documents({"notes": {"$regex": "REFUND REQUIRED"}}) == 1


async def test_expired_link_cancels_order_and_frees_customer(setup_db, tg, rzp):
    db = setup_db
    order = await order_awaiting_payment(db)
    payload = {"event": "payment_link.expired",
               "payload": {"payment_link": {"entity": {"id": "plink_1", "reference_id": order.id}}}}
    assert signed_post(TestClient(app), payload).json()["result"] == "cancelled"
    assert db.query(Order).filter(Order.id == order.id).first().current_state == "CANCELLED"
    assert customer(db).bot_state == "IDLE"


async def test_razorpay_failure_leaves_retry_not_dead_end(setup_db, tg, rzp):
    db = setup_db
    rzp.payment_link.fail = True
    await order_awaiting_payment(db)
    assert any(b.get("callback_data") == "RETRY_PAYMENT" for b in tg.last_buttons())
    rzp.payment_link.fail = False
    await say(db, button="RETRY_PAYMENT")
    assert tg.last_buttons()[0]["url"].startswith("https://rzp.io/")


def test_webhook_disabled_in_demo_mode():
    assert settings.PAYMENT_MODE == "demo"
    res = TestClient(app).post("/webhooks/razorpay", content=b"{}", headers={"X-Razorpay-Signature": "x"})
    assert res.status_code == 404


def test_signature_check_is_strict(monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", WEBHOOK_SECRET)
    body = b'{"a":1}'
    good = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    assert razorpay_service.verify_webhook_signature(body, good)
    assert not razorpay_service.verify_webhook_signature(body, None)
    assert not razorpay_service.verify_webhook_signature(body, "")
    assert not razorpay_service.verify_webhook_signature(b'{"a":2}', good)


def test_production_refuses_unsafe_config(monkeypatch):
    monkeypatch.setattr(settings, "ENV", "production")
    problems = " ".join(validate_settings())
    assert "PAYMENT_MODE=demo" in problems and "SECRET_KEY" in problems and "ADMIN_DEFAULT_PASSWORD" in problems


def test_razorpay_mode_requires_real_keys(monkeypatch):
    monkeypatch.setattr(settings, "PAYMENT_MODE", "razorpay")
    assert any("requires real" in p for p in validate_settings())


def test_production_with_real_config_is_valid(monkeypatch):
    monkeypatch.setattr(settings, "ENV", "production")
    monkeypatch.setattr(settings, "PAYMENT_MODE", "razorpay")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_live_AbCdEf123456")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "live_secret_value")
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setattr(settings, "SECRET_KEY", "x" * 48)
    monkeypatch.setattr(settings, "ADMIN_DEFAULT_PASSWORD", "a-strong-password")
    monkeypatch.setattr(settings, "CORS_ORIGINS", "https://admin.example.com")
    assert validate_settings() == []
