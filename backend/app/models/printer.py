from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class Printer(Base):
    __tablename__ = "printers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    cups_name = Column(String(100), nullable=False, unique=True, index=True)
    model = Column(String(100), default="Generic Printer")
    location = Column(String(100), default="Main Print Room")
    
    status = Column(String(20), default="ONLINE", index=True) # ONLINE, BUSY, OFFLINE, ERROR
    is_online = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)
    is_color_supported = Column(Boolean, default=True)
    supported_paper_sizes = Column(String(100), default="A4,A3,Letter")
    
    # Set when the printer is reported by a paired print agent (PC/phone app) instead of local CUPS.
    agent_id = Column(Integer, nullable=True, index=True)
    last_seen_at = Column(DateTime, nullable=True)

    current_job_id = Column(String(50), nullable=True)
    total_printed_jobs = Column(Integer, default=0)
    error_notes = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    orders = relationship("Order", back_populates="printer")
    print_jobs = relationship("PrintJob", back_populates="printer")
