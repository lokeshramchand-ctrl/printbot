from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class WhatsAppMessage(Base):
    __tablename__ = "whatsapp_messages"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    
    whatsapp_message_id = Column(String(100), nullable=True, index=True)
    direction = Column(String(10), nullable=False) # INBOUND, OUTBOUND
    message_type = Column(String(20), default="text") # text, document, image, button, list, location
    
    text_body = Column(Text, nullable=True)
    media_id = Column(String(100), nullable=True)
    media_url = Column(String(500), nullable=True)
    
    raw_payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    customer = relationship("Customer", back_populates="messages")
