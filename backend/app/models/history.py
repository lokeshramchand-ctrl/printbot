from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(String(30), ForeignKey("orders.id"), nullable=False, index=True)
    
    from_status = Column(String(30), nullable=True)
    to_status = Column(String(30), nullable=False)
    trigger_source = Column(String(30), default="SYSTEM") # SYSTEM, BOT, ADMIN, WEBHOOK, PRINTER
    notes = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    order = relationship("Order", back_populates="history")
