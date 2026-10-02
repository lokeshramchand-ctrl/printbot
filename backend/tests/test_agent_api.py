"""Print agent API: pairing, heartbeat upsert, claim/report, queue interplay."""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.database import MongoSession
from app.main import app
from app.models.order import Order
from app.models.print_job import PrintJob
from app.models.printer import Printer
from app.services import agent_service
from app.services.print_service import print_service
from tests.test_serial_numbering import _make_order, _make_pdf


@pytest.fixture()
def client(setup_db):
    with TestClient(app) as c:
        yield c


def _admin(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _pair(client, name="Counter PC"):
    admin = _admin(client)
    created = client.post("/api/agents", json={"name": name}, headers=admin).json()
    r = client.post("/api/agent/pair", json={"code": created["pairing_code"], "platform": "windows",
                                              "device_name": "PC-1"})
    assert r.status_code == 200, r.text
    return admin, created, {"Authorization": f"Bearer {r.json()['token']}"}


def _clean(db):
    for coll in ("printers", "print_jobs"):
        db.database[coll].delete_many({})


def test_pairing_code_is_single_use_and_token_works(client):
    admin = _admin(client)
    created = client.post("/api/agents", json={"name": "A"}, headers=admin).json()
    assert len(created["pairing_code"]) == 9 and not created["is_paired"]
    code = created["pairing_code"].lower()  # case/dash-insensitive
    assert client.post("/api/agent/pair", json={"code": "ZZZZ-ZZZZ"}).status_code == 400
    ok = client.post("/api/agent/pair", json={"code": code, "platform": "android"})
    assert ok.status_code == 200
    assert client.post("/api/agent/pair", json={"code": code}).status_code == 400
    h = {"Authorization": f"Bearer {ok.json()['token']}"}
    assert client.post("/api/agent/heartbeat", json={"printers": []}, headers=h).status_code == 200
    assert client.post("/api/agent/heartbeat", json={"printers": []}).status_code == 401
    assert client.post("/api/agent/heartbeat", json={}, headers={"Authorization": "Bearer nope"}).status_code == 401
    listed = client.get("/api/agents", headers=admin).json()
    assert listed[0]["is_paired"] and listed[0]["is_online"] and listed[0]["platform"] == "android"


def test_expired_code_rejected(client):
    admin = _admin(client)
    created = client.post("/api/agents", json={"name": "A"}, headers=admin).json()
    MongoSession().database.agents.update_one(
        {"id": created["id"]}, {"$set": {"pairing_expires_at": datetime.utcnow() - timedelta(minutes=1)}})
    assert client.post("/api/agent/pair", json={"code": created["pairing_code"]}).status_code == 400


def test_heartbeat_upserts_printers_without_overriding_admin(client):
    admin, created, h = _pair(client)
    body = {"printers": [{"name": "HP LaserJet", "color": False, "paper_sizes": ["A4", "Letter"]}]}
    client.post("/api/agent/heartbeat", json=body, headers=h)
    printers = client.get("/api/printers", headers=admin).json()
    p = [x for x in printers if x["agent_id"] == created["id"]]
    assert len(p) == 1 and p[0]["name"] == "HP LaserJet" and p[0]["is_online"] and not p[0]["is_color_supported"]
    # admin switches it off; later heartbeats must not turn it back on
    client.put(f"/api/printers/{p[0]['id']}", json={"is_online": False}, headers=admin)
    client.post("/api/agent/heartbeat", json=body, headers=h)
    again = [x for x in client.get("/api/printers", headers=admin).json() if x["agent_id"] == created["id"]]
    assert len(again) == 1 and again[0]["is_online"] is False and again[0]["status"] == "OFFLINE"


def test_full_job_cycle_claim_download_report(client, tmp_path):
    db = MongoSession()
    _clean(db)
    admin, created, h = _pair(client)
    client.post("/api/agent/heartbeat", json={"printers": [{"name": "Epson"}]}, headers=h)
    order = _make_order(db, "PRN-AG-1", _make_pdf(tmp_path))
    job = print_service.submit_job(db, order)
    assert job.printer_id is not None
    # the local executor must NOT print it: it belongs to the agent
    assert print_service.execute_print_job(db, job.id) is False
    assert db.query(PrintJob).filter(PrintJob.id == job.id).first().status == "QUEUED"

    claimed = client.post("/api/agent/jobs/claim", headers=h).json()["job"]
    assert claimed["id"] == job.id and claimed["order_id"] == "PRN-AG-1" and claimed["printer_system_name"] == "Epson"
    assert client.post("/api/agent/jobs/claim", headers=h).json()["job"] is None  # nothing else
    pdf = client.get(claimed["file_url"], headers=h)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert MongoSession().query(Order).filter(Order.id == "PRN-AG-1").first().current_state == "PRINTING"

    r = client.post(f"/api/agent/jobs/{job.id}/report", json={"status": "COMPLETED"}, headers=h)
    assert r.status_code == 200 and r.json()["order_state"] == "COMPLETED"
    assert client.post(f"/api/agent/jobs/{job.id}/report", json={"status": "COMPLETED"}, headers=h).status_code == 409
    printer = MongoSession().query(Printer).filter(Printer.agent_id == created["id"]).first()
    assert printer.status == "ONLINE" and printer.total_printed_jobs == 1


def test_failed_report_marks_print_failed(client, tmp_path):
    db = MongoSession()
    _clean(db)
    admin, created, h = _pair(client)
    client.post("/api/agent/heartbeat", json={"printers": [{"name": "Epson"}]}, headers=h)
    order = _make_order(db, "PRN-AG-2", _make_pdf(tmp_path))
    job = print_service.submit_job(db, order)
    client.post("/api/agent/jobs/claim", headers=h)
    r = client.post(f"/api/agent/jobs/{job.id}/report", json={"status": "FAILED", "error": "out of paper"}, headers=h)
    assert r.json()["order_state"] == "PRINT_FAILED"
    assert MongoSession().query(PrintJob).filter(PrintJob.id == job.id).first().error_message == "out of paper"


def test_waiting_job_is_claimed_once_a_capable_printer_appears(client, tmp_path):
    db = MongoSession()
    _clean(db)
    admin, created, h = _pair(client)
    order = _make_order(db, "PRN-AG-3", _make_pdf(tmp_path))
    order.color_mode = "COLOR"
    db.commit()
    job = print_service.submit_job(db, order)
    assert job.printer_id is None and job.color_mode == "COLOR"
    assert client.post("/api/agent/jobs/claim", headers=h).json()["job"] is None  # no printers yet
    client.post("/api/agent/heartbeat", json={"printers": [{"name": "Mono", "color": False}]}, headers=h)
    assert client.post("/api/agent/jobs/claim", headers=h).json()["job"] is None  # colour job, mono printer
    client.post("/api/agent/heartbeat", json={"printers": [{"name": "Mono", "color": False},
                                                          {"name": "Color", "color": True}]}, headers=h)
    claimed = client.post("/api/agent/jobs/claim", headers=h).json()["job"]
    assert claimed and claimed["printer"]["name"] == "Color"


def test_stale_printer_skipped_and_revoked_agent_locked_out(client, tmp_path):
    db = MongoSession()
    _clean(db)
    admin, created, h = _pair(client)
    client.post("/api/agent/heartbeat", json={"printers": [{"name": "Epson"}]}, headers=h)
    db.database.printers.update_many({}, {"$set": {"last_seen_at": datetime.utcnow() - timedelta(minutes=5)}})
    order = _make_order(db, "PRN-AG-4", _make_pdf(tmp_path))
    assert print_service.submit_job(db, order).printer_id is None  # unreachable printer is skipped
    assert client.delete(f"/api/agents/{created['id']}", headers=admin).status_code == 200
    assert client.post("/api/agent/jobs/claim", headers=h).status_code == 401


def test_silent_agent_job_is_requeued(client, tmp_path):
    db = MongoSession()
    _clean(db)
    admin, created, h = _pair(client)
    client.post("/api/agent/heartbeat", json={"printers": [{"name": "Epson"}]}, headers=h)
    order = _make_order(db, "PRN-AG-5", _make_pdf(tmp_path))
    job = print_service.submit_job(db, order)
    client.post("/api/agent/jobs/claim", headers=h)
    old = datetime.utcnow() - timedelta(minutes=30)
    db.database.print_jobs.update_one({"id": job.id}, {"$set": {"started_at": old}})
    db.database.agents.update_one({"id": created["id"]}, {"$set": {"last_seen_at": old}})
    assert agent_service.requeue_stale_jobs(MongoSession()) == 1
    assert MongoSession().query(PrintJob).filter(PrintJob.id == job.id).first().status == "QUEUED"
