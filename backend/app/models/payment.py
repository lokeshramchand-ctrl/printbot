from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(String(30), ForeignKey("orders.id"), nullable=False, index=True)
    
    razorpay_order_id = Column(String(100), nullable=True, index=True)
    razorpay_payment_id = Column(String(100), nullable=True, index=True)
    razorpay_payment_link_id = Column(String(100), nullable=True, index=True)
    razorpay_payment_link_url = Column(String(500), nullable=True)
    razorpay_signature = Column(String(255), nullable=True)
    
    amount = Column(Float, nullable=False)
    currency = Column(String(10), default="INR")
    status = Column(String(20), default="CREATED", index=True) # CREATED, CAPTURED, FAILED, REFUNDED, EXPIRED
    
    method = Column(String(30), nullable=True) # upi, card, netbanking, wallet
    webhook_event_id = Column(String(100), nullable=True)
    raw_payload = Column(JSON, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    order = relationship("Order", back_populates="payments")
