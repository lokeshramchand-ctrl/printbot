from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON
from datetime import datetime
from app.database import Base

class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String(100), unique=True, nullable=False, index=True) # Unique event ID for idempotency
    provider = Column(String(20), nullable=False) # RAZORPAY, WHATSAPP
    event_type = Column(String(50), nullable=False)
    
    payload = Column(JSON, nullable=True)
    processed = Column(Boolean, default=False)
    error_message = Column(String(500), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
