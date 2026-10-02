"""Live end-to-end check: real HTTP backend (in-memory Mongo) + the real agent code + a real spooler job.

Pairs through the real pairing endpoint, queues an order, lets AgentRunner claim/download/print via GDI
and verifies the printer's output file and the order's final state.

    python e2e_live.py "PrintBot E2E PDF" e2e_out/printed.pdf

The printer must exist on this PC. A "Microsoft Print To PDF" printer whose port is a file path prints
silently to that file (see README, "Verifying real printing").
"""
import os
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(os.path.dirname(ROOT), "backend")
sys.path[:0] = [BACKEND, ROOT]
os.environ.update(MONGODB_URI="mongomock://e2e", MONGODB_DATABASE="printbot_e2e", PAYMENT_MODE="demo",
                  TELEGRAM_BOT_TOKEN="", USE_VIRTUAL_PRINTER="true", ENV="development")
os.chdir(BACKEND)

import fitz  # noqa: E402
import httpx  # noqa: E402
import uvicorn  # noqa: E402

from app.database import MongoSession, initialize_mongodb  # noqa: E402
from app.services.print_service import print_service  # noqa: E402
from printbot_agent import __version__, printers  # noqa: E402
from printbot_agent.api import AgentApi  # noqa: E402
from printbot_agent.config import Settings  # noqa: E402
from printbot_agent.runner import AgentRunner  # noqa: E402

PORT = 8765
BASE = f"http://127.0.0.1:{PORT}"


def wait(cond, what, timeout=40):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return
        time.sleep(0.3)
    raise SystemExit(f"FAIL: timed out waiting for {what}")


def main(printer: str, out_file: str) -> None:
    if os.path.exists(out_file):
        os.remove(out_file)
    server = uvicorn.Server(uvicorn.Config("app.main:app", port=PORT, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    wait(lambda: server.started, "backend start")

    # Dashboard side: create agent, get one-time code.
    tok = httpx.post(f"{BASE}/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
    admin = {"Authorization": f"Bearer {tok}"}
    created = httpx.post(f"{BASE}/api/agents", json={"name": "E2E PC"}, headers=admin).json()

    # Agent side: pair exactly like the GUI does.
    token, name = AgentApi(BASE).pair(created["pairing_code"], "windows", "E2E-PC", __version__)
    settings = Settings(server_url=BASE, token=token, agent_name=name,
                        path=os.path.join(tempfile.mkdtemp(), "config.json"))
    settings.save()
    print(f"paired as {name!r}")

    # Only offer the test printer so the job can't be routed to another device.
    only = lambda color: [p for p in printers.discover(color) if p.name == printer]
    runner = AgentRunner(settings, only, printers.print_pdf)
    runner.start()
    wait(lambda: runner.online, "first heartbeat")
    agents = httpx.get(f"{BASE}/api/agents", headers=admin).json()
    assert agents[0]["is_online"] and agents[0]["printer_count"] == 1, agents
    print("heartbeat ok; agent online with 1 printer")

    # Queue a 2-page paid order.
    pdf = os.path.join(tempfile.mkdtemp(), "doc.pdf")
    d = fitz.open()
    for i in range(2):
        d.new_page(width=595, height=842).insert_text((60, 80), f"PrintBot e2e page {i + 1}", fontsize=24)
    d.save(pdf)
    sys.path.insert(0, os.path.join(BACKEND, "tests"))
    from tests.test_serial_numbering import _make_order  # noqa: E402
    db = MongoSession()
    order = _make_order(db, "PRN-E2E-1", pdf)
    order.total_pages = 2
    db.commit()
    job = print_service.submit_job(db, order)
    print(f"queued job {job.id} serial {order.print_serial}")

    wait(lambda: runner.printed_count == 1 or any(e for _, _, e in runner.log), "job to print")
    for _, msg, err in reversed(runner.log):
        print(("ERR  " if err else "log  ") + msg)
    assert runner.printed_count == 1, "agent did not print"

    wait(lambda: os.path.exists(out_file) and os.path.getsize(out_file) > 0, "spooler output file")
    time.sleep(1)
    out = fitz.open(out_file)
    text = "".join(p.get_text() for p in out)
    print(f"spooled file: {os.path.getsize(out_file)} bytes, {out.page_count} pages")
    assert out.page_count == 2, out.page_count
    assert print_service and MongoSession().database.orders.find_one({"id": "PRN-E2E-1"})["current_state"] == "COMPLETED"
    print("order COMPLETED; E2E PASS")
    runner.stop()
    server.should_exit = True


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "PrintBot E2E PDF",
         os.path.abspath(sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "e2e_out", "printed.pdf")))
