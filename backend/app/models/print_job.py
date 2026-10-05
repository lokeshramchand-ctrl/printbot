from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class PrintJob(Base):
    __tablename__ = "print_jobs"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(String(30), ForeignKey("orders.id"), nullable=False, index=True)
    printer_id = Column(Integer, ForeignKey("printers.id"), nullable=True, index=True)
    
    cups_job_id = Column(Integer, nullable=True)
    status = Column(String(20), default="QUEUED", index=True) # QUEUED, PRINTING, COMPLETED, FAILED, CANCELLED
    
    copies = Column(Integer, default=1)
    paper_size = Column(String(10), default="A4")
    color_mode = Column(String(10), default="BW")
    sides = Column(String(15), default="single")
    total_pages = Column(Integer, default=1)
    
    priority = Column(Integer, default=10) # Lower number = higher priority
    retry_count = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)

    # Denormalized copy of Order.print_serial at the time this job was
    # created, so the serial is visible on the job record itself (queue
    # views, logs, audit trail) without an extra join.
    print_serial = Column(String(40), nullable=True, index=True)

    # Monotonically increasing, transaction-safe queue position — assigned
    # once when the job is created (see print_service.submit_job) and never
    # reassigned, so the original queue order stays auditable even if jobs
    # are retried, force-printed out of turn, or the process restarts.
    queue_sequence = Column(Integer, nullable=True, index=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    order = relationship("Order", back_populates="print_jobs")
    printer = relationship("Printer", back_populates="print_jobs")
