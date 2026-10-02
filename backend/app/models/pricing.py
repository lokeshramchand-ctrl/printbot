from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime
from datetime import datetime
from app.database import Base

class PricingRule(Base):
    __tablename__ = "pricing_rules"

    id = Column(Integer, primary_key=True, index=True)
    paper_size = Column(String(10), nullable=False) # A4, A3, Letter
    is_color = Column(Boolean, default=False)       # False = B&W, True = Color
    is_double_sided = Column(Boolean, default=False)# False = Single-sided, True = Double-sided
    
    price_per_page = Column(Float, nullable=False)   # e.g., 2.0 for A4 B&W, 10.0 for A4 Color
    min_order_price = Column(Float, default=5.0)     # Minimum order price
    additional_charge = Column(Float, default=0.0)  # Binding / Service fee if any
    
    is_active = Column(Boolean, default=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
