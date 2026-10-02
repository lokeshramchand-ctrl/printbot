from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class Order(Base):
    __tablename__ = "orders"

    id = Column(String(30), primary_key=True, index=True) # PRN-000001 format
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    channel = Column(String(20), default="WHATSAPP", index=True) # WHATSAPP, TELEGRAM
    
    # Document details
    original_file_name = Column(String(255), nullable=True)
    stored_file_path = Column(String(500), nullable=True)
    printable_pdf_path = Column(String(500), nullable=True)
    file_type = Column(String(10), nullable=True) # PDF, DOC, DOCX, JPG, PNG
    file_size_bytes = Column(Integer, default=0)
    
    # Print preferences
    total_pages = Column(Integer, default=1)
    copies = Column(Integer, default=1)
    paper_size = Column(String(10), default="A4") # A4, A3, Letter
    color_mode = Column(String(10), default="BW") # BW, Color
    sides = Column(String(15), default="single") # single, double
    pages_to_print = Column(String(50), default="all") # all, or range e.g. "1-5"
    
    # Pricing & Payment
    rate_per_page = Column(Float, default=0.0)
    subtotal_amount = Column(Float, default=0.0)
    additional_charges = Column(Float, default=0.0)
    total_amount = Column(Float, default=0.0) # In INR (₹)
    payment_status = Column(String(20), default="PENDING", index=True) # PENDING, PAID, FAILED, REFUNDED
    
    # Printing & Execution
    current_state = Column(String(30), default="UPLOADED", index=True)
    print_status = Column(String(20), default="NOT_QUEUED", index=True) # NOT_QUEUED, QUEUED, PRINTING, COMPLETED, FAILED
    printer_id = Column(Integer, ForeignKey("printers.id"), nullable=True)
    failure_reason = Column(Text, nullable=True)

    # Print serial / reference number. Generated once (via SerialCounter,
    # see app/services/serial_service.py) the first time the order enters
    # the print queue, and reused on every retry/reprint so the value stays
    # deterministic for the lifetime of the order. Stamped in a small
    # header/footer on every page of the *printable* PDF (never the
    # customer's original upload) so staff can match a loose page in a
    # stack back to the correct order at a glance.
    print_serial = Column(String(40), unique=True, nullable=True, index=True)
    serial_stamped_at = Column(DateTime, nullable=True)  # set once the PDF has been stamped (idempotency guard)
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    customer = relationship("Customer", back_populates="orders")
    printer = relationship("Printer", back_populates="orders")
    payments = relationship("Payment", back_populates="order")
    print_jobs = relationship("PrintJob", back_populates="order")
    history = relationship("OrderStatusHistory", back_populates="order", cascade="all, delete-orphan")
    uploaded_files = relationship("UploadedFile", back_populates="order", cascade="all, delete-orphan")
