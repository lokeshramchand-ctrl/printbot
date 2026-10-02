from sqlalchemy import Column, Integer, String, DateTime, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    channel = Column(String(20), default="WHATSAPP", nullable=False, index=True) # WHATSAPP, TELEGRAM
    whatsapp_number = Column(String(50), nullable=True, index=True)
    telegram_chat_id = Column(String(50), nullable=True, index=True)
    
    display_name = Column(String(100), nullable=True)
    bot_state = Column(String(50), default="IDLE", nullable=False)
    state_data = Column(JSON, default=dict) # Stores draft order selections during conversation
    active_order_id = Column(String(30), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    orders = relationship("Order", back_populates="customer")
    messages = relationship("WhatsAppMessage", back_populates="customer")
