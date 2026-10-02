"""Print agents: pairing, heartbeat (printer upsert), job claim and result reporting.

An agent is a thin client (Windows app, Android app, ...) that talks to the
backend over HTTP only; nothing here assumes an operating system. The backend
never pushes to an agent -- the agent polls, so it works behind any NAT.
"""
import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional

from app.models.agent import Agent
from app.models.history import OrderStatusHistory
from app.models.order import Order
from app.models.print_job import PrintJob
from app.models.printer import Printer
from app.services.print_service import AGENT_STALE_SECONDS, printer_reachable

logger = logging.getLogger("agent_service")

PAIRING_TTL_MINUTES = 15
JOB_STALE_MINUTES = 10  # a claimed job whose agent went silent this long goes back to the queue
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O/1/I/L


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def normalize_code(code: str) -> str:
    return "".join(c for c in (code or "").upper() if c.isalnum())


def issue_pairing_code(agent: Agent) -> str:
    """New one-time code (shown as XXXX-XXXX). Invalidates any existing token (re-pairing)."""
    raw = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))
    agent.pairing_code_hash = _hash(raw)
    agent.pairing_expires_at = datetime.utcnow() + timedelta(minutes=PAIRING_TTL_MINUTES)
    agent.token_hash = None
    agent.paired_at = None
    return f"{raw[:4]}-{raw[4:]}"


def pair(db, code: str, platform: Optional[str], device_name: Optional[str],
         app_version: Optional[str]) -> Optional[tuple[Agent, str]]:
    """Exchange a pairing code for a bearer token (returned once). None if invalid/expired."""
    normalized = normalize_code(code)
    if len(normalized) != 8:
        return None
    # Atomic: the code is consumed by whoever claims it first.
    claimed = db.database.agents.find_one_and_update(
        {"pairing_code_hash": _hash(normalized), "is_active": True,
         "pairing_expires_at": {"$gt": datetime.utcnow()}},
        {"$set": {"pairing_code_hash": None, "pairing_expires_at": None}},
    )
    if claimed is None:
        return None
    token = secrets.token_urlsafe(32)
    now = datetime.utcnow()
    db.database.agents.update_one({"id": claimed["id"]}, {"$set": {
        "token_hash": _hash(token), "paired_at": now, "last_seen_at": now,
        "platform": (platform or "")[:30] or None,
        "device_name": (device_name or "")[:100] or None,
        "app_version": (app_version or "")[:30] or None,
    }})
    agent = db.query(Agent).filter(Agent.id == claimed["id"]).first()
    return agent, token


def authenticate(db, token: str) -> Optional[Agent]:
    if not token:
        return None
    th = _hash(token)
    agent = db.query(Agent).filter(Agent.token_hash == th).first()
    if agent and agent.is_active and agent.token_hash and hmac.compare_digest(agent.token_hash, th):
        return agent
    return None


def agent_online(agent: Agent) -> bool:
    return bool(agent.last_seen_at) and (datetime.utcnow() - agent.last_seen_at).total_seconds() <= AGENT_STALE_SECONDS


def _printer_key(agent: Agent, system_name: str) -> str:
    return f"agent{agent.id}:{system_name}"[:100]


def heartbeat(db, agent: Agent, reported: list[dict]) -> list[Printer]:
    """Record liveness and upsert the printers this agent can reach.

    New printers start ON (admin can switch them off); an admin's on/off choice,
    name and default flag are never overwritten by later heartbeats.
    Printers the agent stopped reporting simply go stale (unreachable).
    """
    now = datetime.utcnow()
    agent.last_seen_at = now
    seen: list[Printer] = []
    for item in reported:
        system_name = (item.get("name") or "").strip()
        if not system_name:
            continue
        key = _printer_key(agent, system_name)
        printer = db.query(Printer).filter(Printer.cups_name == key).first()
        if printer is None:
            printer = Printer(
                name=system_name[:100], cups_name=key, model=(item.get("model") or "Generic Printer")[:100],
                location=(agent.name or "Agent")[:100], agent_id=agent.id, is_online=True,
                is_color_supported=bool(item.get("color", True)),
                supported_paper_sizes=",".join(item.get("paper_sizes") or ["A4"])[:100],
                status="ONLINE",
            )
            db.add(printer)
        else:
            printer.agent_id = agent.id
            if item.get("model"):
                printer.model = item["model"][:100]
            printer.is_color_supported = bool(item.get("color", printer.is_color_supported))
            if item.get("paper_sizes"):
                printer.supported_paper_sizes = ",".join(item["paper_sizes"])[:100]
            if item.get("state") == "error":
                printer.status = "ERROR"
            elif printer.is_online and printer.status != "BUSY":
                printer.status = "ONLINE"
            elif not printer.is_online:
                printer.status = "OFFLINE"
        printer.last_seen_at = now
        seen.append(printer)
    db.commit()
    return seen


def refresh_printer_statuses(db) -> None:
    """Mark agent printers that stopped heartbeating as OFFLINE (lazy; called when listing)."""
    changed = False
    for p in db.query(Printer).all():
        if p.agent_id and not printer_reachable(p) and p.status != "OFFLINE":
            p.status = "OFFLINE"
            changed = True
    if changed:
        db.commit()


def requeue_stale_jobs(db) -> int:
    """Jobs claimed by an agent that has since gone silent return to the queue."""
    cutoff = datetime.utcnow() - timedelta(minutes=JOB_STALE_MINUTES)
    n = 0
    for job in db.query(PrintJob).filter(PrintJob.status == "PRINTING").all():
        if not job.agent_id or not job.started_at or job.started_at > cutoff:
            continue
        agent = db.query(Agent).filter(Agent.id == job.agent_id).first()
        if agent and agent.last_seen_at and agent.last_seen_at > cutoff:
            continue
        reset = db.database.print_jobs.find_one_and_update(
            {"id": job.id, "status": "PRINTING"},
            {"$set": {"status": "QUEUED", "agent_id": None, "printer_id": None, "started_at": None,
                      "error_message": "Agent went silent; job re-queued."}})
        if reset is None:
            continue
        db.database.orders.update_one({"id": job.order_id, "current_state": "PRINTING"},
                                      {"$set": {"current_state": "QUEUED", "print_status": "QUEUED"}})
        if job.printer_id:
            db.database.printers.update_one({"id": job.printer_id},
                                            {"$set": {"status": "ONLINE", "current_job_id": None}})
        n += 1
    return n


def _capable(printer: Printer, job: PrintJob) -> bool:
    if (job.color_mode or "").upper() == "COLOR" and not printer.is_color_supported:
        return False
    sizes = {x.strip().upper() for x in (printer.supported_paper_sizes or "").split(",") if x.strip()}
    return not (job.paper_size and sizes and job.paper_size.upper() not in sizes)


def claim_next_job(db, agent: Agent) -> Optional[tuple[PrintJob, Printer, Order]]:
    """Atomically claim the oldest QUEUED job one of this agent's printers can print."""
    requeue_stale_jobs(db)
    mine = [p for p in db.query(Printer).filter(Printer.agent_id == agent.id).all()
            if p.is_online and printer_reachable(p)]
    if not mine:
        return None
    mine_ids = {p.id for p in mine}
    jobs = db.query(PrintJob).filter(PrintJob.status == "QUEUED").all()
    jobs.sort(key=lambda j: (j.queue_sequence or 0, j.id))
    all_printers = {p.id: p for p in db.query(Printer).all()}

    for job in jobs:
        order = db.query(Order).filter(Order.id == job.order_id).first()
        if order is None:
            continue
        if order.current_state in ("CANCELLED", "REFUNDED"):
            db.database.print_jobs.update_one({"id": job.id, "status": "QUEUED"}, {"$set": {"status": "CANCELLED"}})
            continue
        if not order.printable_pdf_path:
            continue
        assigned = all_printers.get(job.printer_id) if job.printer_id else None
        if assigned and assigned.id in mine_ids and _capable(assigned, job):
            target = assigned
        elif assigned is None or not (assigned.is_online and printer_reachable(assigned)):
            # Unassigned, or its printer is off/unreachable: any capable printer of ours may take it.
            options = sorted((p for p in mine if _capable(p, job)),
                             key=lambda p: (p.status == "BUSY", p.total_printed_jobs or 0, p.id))
            if not options:
                continue
            target = options[0]
        else:
            continue  # assigned to another live printer (local or another agent)

        won = db.database.print_jobs.find_one_and_update(
            {"id": job.id, "status": "QUEUED"},
            {"$set": {"status": "PRINTING", "agent_id": agent.id, "printer_id": target.id,
                      "started_at": datetime.utcnow()}})
        if won is None:
            continue  # another agent beat us to it
        db.database.orders.update_one({"id": order.id}, {"$set": {
            "current_state": "PRINTING", "print_status": "PRINTING", "printer_id": target.id}})
        db.database.printers.update_one({"id": target.id},
                                        {"$set": {"status": "BUSY", "current_job_id": order.id}})
        db.add(OrderStatusHistory(order_id=order.id, from_status="QUEUED", to_status="PRINTING",
                                  trigger_source="AGENT",
                                  notes=f"Claimed by agent '{agent.name}' for printer {target.name}"))
        db.commit()
        db.refresh(job)
        db.refresh(order)
        db.refresh(target)
        return job, target, order
    return None


def finish_job(db, agent: Agent, job_id: int, success: bool,
               error: Optional[str]) -> Optional[tuple[PrintJob, Order]]:
    """Record the agent's result. None if the job isn't this agent's PRINTING job."""
    update = {"status": "COMPLETED" if success else "FAILED",
              "completed_at": datetime.utcnow() if success else None}
    if not success:
        update["error_message"] = (error or "Agent reported a print failure")[:1000]
    done = db.database.print_jobs.find_one_and_update(
        {"id": job_id, "status": "PRINTING", "agent_id": agent.id}, {"$set": update})
    if done is None:
        return None
    if not success:
        db.database.print_jobs.update_one({"id": job_id}, {"$inc": {"retry_count": 1}})
    order_state = "COMPLETED" if success else "PRINT_FAILED"
    db.database.orders.update_one({"id": done["order_id"]}, {"$set": {
        "current_state": order_state, "print_status": "COMPLETED" if success else "FAILED"}})
    if done.get("printer_id"):
        printer_update: dict = {"$set": {"status": "ONLINE" if success else "ERROR", "current_job_id": None}}
        if success:
            printer_update["$inc"] = {"total_printed_jobs": 1}
        else:
            printer_update["$set"]["error_notes"] = (error or "")[:500] or None
        db.database.printers.update_one({"id": done["printer_id"]}, printer_update)
    db.add(OrderStatusHistory(
        order_id=done["order_id"], from_status="PRINTING", to_status=order_state, trigger_source="AGENT",
        notes=(f"Printed by agent '{agent.name}' (serial {done.get('print_serial')})." if success
               else f"Agent '{agent.name}' failed: {error or 'unknown error'}")))
    db.commit()
    job = db.query(PrintJob).filter(PrintJob.id == job_id).first()
    order = db.query(Order).filter(Order.id == done["order_id"]).first()
    return job, order
