from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class PrinterCreate(BaseModel):
    name: str
    cups_name: str
    model: Optional[str] = "Generic Printer"
    location: Optional[str] = "Main Store"
    is_color_supported: bool = True
    supported_paper_sizes: str = "A4,A3,Letter"
    is_default: bool = False
    is_online: bool = True

class PrinterUpdate(BaseModel):
    name: Optional[str] = None
    model: Optional[str] = None
    location: Optional[str] = None
    status: Optional[str] = None
    is_online: Optional[bool] = None
    is_color_supported: Optional[bool] = None
    supported_paper_sizes: Optional[str] = None
    is_default: Optional[bool] = None
    cups_name: Optional[str] = None

class PrinterOut(BaseModel):
    id: int
    name: str
    cups_name: str
    model: str
    location: str
    status: str
    is_online: bool
    is_default: bool
    is_color_supported: bool
    supported_paper_sizes: str
    current_job_id: Optional[str] = None
    agent_id: Optional[int] = None
    last_seen_at: Optional[datetime] = None
    total_printed_jobs: int
    updated_at: datetime

    class Config:
        from_attributes = True
