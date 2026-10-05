from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import os
import fitz
from app.database import get_db
from app.models.admin import Admin
from app.models.printer import Printer
from app.schemas.printer import PrinterCreate, PrinterUpdate, PrinterOut
from app.api.auth import get_current_admin
from app.services.print_service import print_service
from app.services import payment_service
from app.config import settings

router = APIRouter(prefix="/api/printers", tags=["Printers"])

@router.get("", response_model=List[PrinterOut])
def get_printers(
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    """List printers and sync status from CUPS."""
    printers = print_service.sync_printers(db)
    return printers

def _apply_power_state(printer: Printer) -> None:
    if not printer.is_online:
        printer.status = "OFFLINE"
    elif printer.status in ("OFFLINE", "ERROR"):
        printer.status = "ONLINE"


def _single_default(db: Session, printer: Printer) -> None:
    if printer.is_default:
        for other in db.query(Printer).filter(Printer.is_default == True).all():
            if other.id != printer.id:
                other.is_default = False


@router.post("", response_model=PrinterOut)
async def create_printer(
    req: PrinterCreate,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    """Add a new printer configuration."""
    existing = db.query(Printer).filter(Printer.cups_name == req.cups_name).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Printer with CUPS name '{req.cups_name}' already exists")

    if req.connection_type == "WIFI":
        if not (req.connection_uri or "").lower().startswith(("ipp://", "ipps://", "socket://", "http://", "https://")):
            raise HTTPException(status_code=400, detail="WIFI printers need an ipp://, ipps://, socket:// or http(s):// connection_uri")
        error = print_service.register_network_printer(req.cups_name, req.connection_uri)
        if error:
            raise HTTPException(status_code=502, detail=f"CUPS could not add the printer: {error}")

    printer = Printer(**req.model_dump())
    _apply_power_state(printer)
    db.add(printer)
    db.commit()
    _single_default(db, printer)
    db.commit()
    db.refresh(printer)
    if printer.is_online:
        await payment_service.drain_print_queue(db)
    return printer

@router.put("/{printer_id}", response_model=PrinterOut)
async def update_printer(
    printer_id: int,
    req: PrinterUpdate,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    """Update printer details, paper sizes, or online status."""
    printer = db.query(Printer).filter(Printer.id == printer_id).first()
    if not printer:
        raise HTTPException(status_code=404, detail="Printer not found")

    changes = req.model_dump(exclude_unset=True)
    new_cups = changes.get("cups_name")
    if new_cups and new_cups != printer.cups_name:
        if db.query(Printer).filter(Printer.cups_name == new_cups).first():
            raise HTTPException(status_code=400, detail=f"Printer with CUPS name '{new_cups}' already exists")
    for key, val in changes.items():
        setattr(printer, key, val)
    _apply_power_state(printer)
    _single_default(db, printer)

    db.commit()
    db.refresh(printer)
    # Switching a printer on releases everything that piled up while all were off.
    if printer.is_online:
        await payment_service.drain_print_queue(db)
    return printer

@router.post("/{printer_id}/test-print")
def send_test_print(
    printer_id: int,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    """Generate and dispatch test page to selected printer."""
    printer = db.query(Printer).filter(Printer.id == printer_id).first()
    if not printer:
        raise HTTPException(status_code=404, detail="Printer not found")

    # Generate test page PDF
    test_pdf_path = os.path.join(settings.STORAGE_DIR, "processed", f"test_print_{printer.id}.pdf")
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((100, 100), f"PrintBot Test Page - {printer.name}", fontsize=20)
    page.insert_text((100, 140), f"Printer Model: {printer.model}", fontsize=12)
    page.insert_text((100, 160), f"Status: {printer.status} | Location: {printer.location}", fontsize=12)
    doc.save(test_pdf_path)
    doc.close()

    return {"status": "success", "message": f"Test print page sent to {printer.name}", "pdf_path": test_pdf_path}
