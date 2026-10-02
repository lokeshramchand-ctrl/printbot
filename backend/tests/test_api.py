"""Admin API, WebSocket auth, webhook hardening and retention against in-memory Mongo."""
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.config import settings
from app.main import app
from app.models.order import Order
from app.services import cleanup_service
from test_bot_flow import say, upto_sides, tg  # noqa: F401  (fixtures)


@pytest.fixture
def client(setup_db):
    with TestClient(app) as c:  # runs startup: indexes, admin + pricing seed
        yield c


def login(client):
    res = client.post("/api/auth/login", json={"username": settings.ADMIN_DEFAULT_USERNAME,
                                                 "password": settings.ADMIN_DEFAULT_PASSWORD})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


def auth(client):
    return {"Authorization": f"Bearer {login(client)}"}


def test_health_and_root(client):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/").json()["payment_mode"] == "demo"


def test_orders_require_auth(client):
    assert client.get("/api/orders").status_code == 401


async def test_orders_list_search_and_actions(setup_db, tg, client):
    db = setup_db
    await upto_sides(db)
    await say(db, button="SIDES_SINGLE")
    order = db.query(Order).first()
    headers = auth(client)

    listed = client.get("/api/orders", headers=headers).json()
    assert [o["id"] for o in listed] == [order.id]
    assert client.get("/api/orders", params={"q": "file_v1"}, headers=headers).json()
    assert client.get("/api/orders", params={"q": "zzz-nothing"}, headers=headers).json() == []
    assert client.get("/api/orders", params={"status": "PAYMENT_PENDING"}, headers=headers).json()

    # An unpaid order must never be printable by clicking PRINT.
    res = client.post(f"/api/orders/{order.id}/action", json={"action": "PRINT"}, headers=headers)
    assert res.status_code == 400

    res = client.post(f"/api/orders/{order.id}/action", json={"action": "CANCEL"}, headers=headers)
    assert res.json()["new_state"] == "CANCELLED"
    assert any("cancelled by the shop admin" in t for t in tg.texts()), "Telegram customer notified on Telegram"
    # Cancelled -> customer is released from WAITING_FOR_PAYMENT.
    await say(db, "hi")
    assert any("Welcome" in t for t in tg.texts())


async def test_admin_refund_of_paid_order(setup_db, tg, client):
    db = setup_db
    await upto_sides(db)
    await say(db, button="SIDES_SINGLE")
    order_id = db.query(Order).first().id
    await say(db, button=f"DEMO_PAY_{order_id}")
    headers = auth(client)
    assert client.post(f"/api/orders/{order_id}/action", json={"action": "REFUND"}, headers=headers).status_code == 200
    assert db.query(Order).filter(Order.id == order_id).first().payment_status == "REFUNDED"
    # Refunded orders cannot be re-printed for free.
    res = client.post(f"/api/orders/{order_id}/action", json={"action": "PRINT"}, headers=headers)
    assert res.status_code == 400


def test_websocket_requires_valid_token(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws"):
            pass
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws?token=garbage"):
            pass
    with client.websocket_connect(f"/ws?token={login(client)}") as ws:
        ws.send_text("ping")
        assert ws.receive_text() == "pong"


def test_telegram_webhook_secret_enforced(client, monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_WEBHOOK_SECRET", "s3cret")
    body = {"update_id": 1}
    assert client.post("/webhooks/telegram", json=body).status_code == 403
    ok = client.post("/webhooks/telegram", json=body, headers={"X-Telegram-Bot-Api-Secret-Token": "s3cret"})
    assert ok.status_code == 200


def test_telegram_setup_requires_admin(client):
    assert client.get("/webhooks/telegram/setup", params={"url": "https://x.example"}).status_code == 401


def test_whatsapp_signature_enforced(client, monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_APP_SECRET", "appsecret")
    body = json.dumps({"entry": []}).encode()
    assert client.post("/webhooks/whatsapp", content=body).status_code == 403
    sig = "sha256=" + hmac.new(b"appsecret", body, hashlib.sha256).hexdigest()
    assert client.post("/webhooks/whatsapp", content=body, headers={"X-Hub-Signature-256": sig}).status_code == 200


def test_cors_is_not_wildcard_with_credentials(client):
    res = client.options("/api/orders", headers={"Origin": "https://evil.example",
                                                   "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in res.headers


def test_uploads_are_not_publicly_served(client):
    assert client.get("/storage/uploads/anything.pdf").status_code == 404
    assert client.get("/storage/processed/PRN-1/printable.pdf").status_code == 404


async def test_retention_deletes_old_finished_order_files(setup_db, tg):
    db = setup_db
    await upto_sides(db)
    await say(db, button="SIDES_SINGLE")
    order_id = db.query(Order).first().id
    await say(db, button=f"DEMO_PAY_{order_id}")
    order = db.query(Order).filter(Order.id == order_id).first()
    assert os.path.exists(order.stored_file_path) and os.path.exists(order.printable_pdf_path)

    # Fresh orders are kept...
    assert cleanup_service.purge_expired_files(db)["orders"] == 0
    assert os.path.exists(order.stored_file_path)
    # ...old finished ones are purged exactly once.
    order.updated_at = datetime.utcnow() - timedelta(days=settings.FILE_RETENTION_DAYS + 1)
    db.commit()
    assert cleanup_service.purge_expired_files(db)["orders"] == 1
    assert not os.path.exists(order.stored_file_path) and not os.path.exists(order.printable_pdf_path)
    assert cleanup_service.purge_expired_files(db)["orders"] == 0
