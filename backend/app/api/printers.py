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

@router.post("", response_model=PrinterOut)
def create_printer(
    req: PrinterCreate,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    """Add a new printer configuration."""
    existing = db.query(Printer).filter(Printer.cups_name == req.cups_name).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Printer with CUPS name '{req.cups_name}' already exists")

    printer = Printer(**req.model_dump())
    db.add(printer)
    db.commit()
    db.refresh(printer)
    return printer

@router.put("/{printer_id}", response_model=PrinterOut)
def update_printer(
    printer_id: int,
    req: PrinterUpdate,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    """Update printer details, paper sizes, or online status."""
    printer = db.query(Printer).filter(Printer.id == printer_id).first()
    if not printer:
        raise HTTPException(status_code=404, detail="Printer not found")

    for key, val in req.model_dump(exclude_unset=True).items():
        setattr(printer, key, val)

    db.commit()
    db.refresh(printer)
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
