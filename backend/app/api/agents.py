"""Print agents.

* ``/api/agents``  -- dashboard (admin JWT): create agents, show pairing codes, revoke.
* ``/api/agent``   -- the agent apps (agent bearer token): pair, heartbeat, claim, file, report.

The device API is plain JSON/HTTP with no OS assumptions, so a Windows app, an
Android app or a script can all be agents.
"""
import os
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth import get_current_admin
from app.database import get_db
from app.models.admin import Admin
from app.models.agent import Agent
from app.models.print_job import PrintJob
from app.models.printer import Printer
from app.services import agent_service, payment_service
from app.services.print_service import AGENT_STALE_SECONDS
from app.services.websocket_service import manager as websocket_manager

admin_router = APIRouter(prefix="/api/agents", tags=["Agents"])
router = APIRouter(prefix="/api/agent", tags=["Agent device API"])


# ───────────────────────── dashboard side ─────────────────────────

class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class AgentOut(BaseModel):
    id: int
    name: str
    platform: Optional[str] = None
    device_name: Optional[str] = None
    app_version: Optional[str] = None
    is_paired: bool
    is_online: bool
    last_seen_at: Optional[datetime] = None
    paired_at: Optional[datetime] = None
    pairing_expires_at: Optional[datetime] = None
    printer_count: int = 0


class AgentCreated(AgentOut):
    pairing_code: str


def _out(db, agent: Agent) -> dict:
    return {
        "id": agent.id, "name": agent.name, "platform": agent.platform, "device_name": agent.device_name,
        "app_version": agent.app_version, "is_paired": bool(agent.token_hash),
        "is_online": agent_service.agent_online(agent), "last_seen_at": agent.last_seen_at,
        "paired_at": agent.paired_at,
        "pairing_expires_at": agent.pairing_expires_at if agent.pairing_code_hash else None,
        "printer_count": db.query(Printer).filter(Printer.agent_id == agent.id).count(),
    }


@admin_router.get("", response_model=List[AgentOut])
def list_agents(db: Session = Depends(get_db), admin: Admin = Depends(get_current_admin)):
    agents = db.query(Agent).filter(Agent.is_active == True).all()
    return [_out(db, a) for a in agents]


@admin_router.post("", response_model=AgentCreated)
def create_agent(req: AgentCreate, db: Session = Depends(get_db), admin: Admin = Depends(get_current_admin)):
    agent = Agent(name=req.name.strip(), is_active=True)
    code = agent_service.issue_pairing_code(agent)
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return {**_out(db, agent), "pairing_code": code}


@admin_router.post("/{agent_id}/pairing-code", response_model=AgentCreated)
def new_pairing_code(agent_id: int, db: Session = Depends(get_db), admin: Admin = Depends(get_current_admin)):
    """Re-pair: issues a fresh code and revokes the current token."""
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.is_active == True).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    code = agent_service.issue_pairing_code(agent)
    db.commit()
    return {**_out(db, agent), "pairing_code": code}


@admin_router.delete("/{agent_id}")
async def remove_agent(agent_id: int, db: Session = Depends(get_db), admin: Admin = Depends(get_current_admin)):
    """Revoke an agent: its token stops working, its printers go off, its in-flight job is re-queued."""
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.is_active == True).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent.is_active = False
    agent.token_hash = None
    agent.pairing_code_hash = None
    for p in db.query(Printer).filter(Printer.agent_id == agent.id).all():
        p.is_online = False
        p.status = "OFFLINE"
        p.current_job_id = None
    db.commit()
    for job in db.query(PrintJob).filter(PrintJob.agent_id == agent.id, PrintJob.status == "PRINTING").all():
        db.database.print_jobs.update_one({"id": job.id, "status": "PRINTING"}, {"$set": {
            "status": "QUEUED", "agent_id": None, "printer_id": None, "started_at": None}})
        db.database.orders.update_one({"id": job.order_id, "current_state": "PRINTING"},
                                      {"$set": {"current_state": "QUEUED", "print_status": "QUEUED"}})
    await websocket_manager.broadcast_event("printers_updated", {})
    return {"status": "removed"}


# ───────────────────────── device side ─────────────────────────

def get_current_agent(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> Agent:
    scheme, _, token = authorization.partition(" ")
    agent = agent_service.authenticate(db, token.strip()) if scheme.lower() == "bearer" else None
    if agent is None:
        raise HTTPException(status_code=401, detail="Invalid or revoked agent token")
    return agent


class PairRequest(BaseModel):
    code: str
    platform: Optional[str] = None
    device_name: Optional[str] = None
    app_version: Optional[str] = None


class PairResponse(BaseModel):
    token: str
    agent_id: int
    agent_name: str


@router.post("/pair", response_model=PairResponse)
def pair(req: PairRequest, db: Session = Depends(get_db)):
    result = agent_service.pair(db, req.code, req.platform, req.device_name, req.app_version)
    if result is None:
        raise HTTPException(status_code=400, detail="Invalid or expired pairing code")
    agent, token = result
    return PairResponse(token=token, agent_id=agent.id, agent_name=agent.name)


class ReportedPrinter(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    model: Optional[str] = None
    color: bool = True
    paper_sizes: List[str] = ["A4"]
    state: Optional[str] = None  # "ok" | "error"


class HeartbeatRequest(BaseModel):
    printers: List[ReportedPrinter] = []
    app_version: Optional[str] = None


@router.post("/heartbeat")
async def heartbeat(req: HeartbeatRequest, db: Session = Depends(get_db), agent: Agent = Depends(get_current_agent)):
    if req.app_version:
        agent.app_version = req.app_version[:30]
    was_stale = not agent_service.agent_online(agent)
    printers = agent_service.heartbeat(db, agent, [p.model_dump() for p in req.printers])
    queued = db.query(PrintJob).filter(PrintJob.status == "QUEUED").count()
    if was_stale or req.printers:
        await websocket_manager.broadcast_event("printers_updated", {"agent_id": agent.id})
    return {
        "agent_id": agent.id,
        "printers": [{"id": p.id, "name": p.name, "is_online": p.is_online} for p in printers],
        "queued_jobs": queued,
        "poll_interval_seconds": 5,
        "stale_after_seconds": AGENT_STALE_SECONDS,
    }


@router.post("/jobs/claim")
async def claim(db: Session = Depends(get_db), agent: Agent = Depends(get_current_agent)):
    """Claim the next job. Returns {"job": null} when there is nothing to print."""
    agent.last_seen_at = datetime.utcnow()
    db.commit()
    claimed = agent_service.claim_next_job(db, agent)
    if claimed is None:
        return {"job": None}
    job, printer, order = claimed
    await websocket_manager.broadcast_event("order_updated", {"order_id": order.id, "status": "PRINTING"})
    return {"job": {
        "id": job.id, "order_id": order.id, "serial": job.print_serial,
        "printer": {"id": printer.id, "name": printer.name},
        # Name the printer by what the agent reported, not by the admin-editable display name.
        "printer_system_name": printer.cups_name.split(":", 1)[-1],
        "copies": job.copies, "paper_size": job.paper_size, "color_mode": job.color_mode,
        "sides": job.sides, "total_pages": job.total_pages,
        "file_url": f"/api/agent/jobs/{job.id}/file",
    }}


@router.get("/jobs/{job_id}/file")
def job_file(job_id: int, db: Session = Depends(get_db), agent: Agent = Depends(get_current_agent)):
    job = db.query(PrintJob).filter(PrintJob.id == job_id).first()
    if not job or job.agent_id != agent.id or job.status != "PRINTING":
        raise HTTPException(status_code=404, detail="No such job claimed by this agent")
    order = job.order
    if not order or not order.printable_pdf_path or not os.path.exists(order.printable_pdf_path):
        raise HTTPException(status_code=404, detail="Printable file missing")
    return FileResponse(order.printable_pdf_path, media_type="application/pdf",
                        filename=f"{job.print_serial or order.id}.pdf")


class JobReport(BaseModel):
    status: str  # COMPLETED | FAILED
    error: Optional[str] = None


@router.post("/jobs/{job_id}/report")
async def report(job_id: int, req: JobReport, db: Session = Depends(get_db),
                 agent: Agent = Depends(get_current_agent)):
    status = req.status.upper()
    if status not in ("COMPLETED", "FAILED"):
        raise HTTPException(status_code=422, detail="status must be COMPLETED or FAILED")
    agent.last_seen_at = datetime.utcnow()
    result = agent_service.finish_job(db, agent, job_id, status == "COMPLETED", req.error)
    if result is None:
        raise HTTPException(status_code=409, detail="Job is not currently claimed by this agent")
    job, order = result
    db.refresh(order)
    await payment_service.notify_print_result(order, status == "COMPLETED")
    await websocket_manager.broadcast_event("printers_updated", {"agent_id": agent.id})
    return {"status": "ok", "order_state": order.current_state}
