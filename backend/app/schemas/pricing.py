from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class PricingRuleCreate(BaseModel):
    paper_size: str  # A4, A3, Letter
    is_color: bool
    is_double_sided: bool
    price_per_page: float
    min_order_price: float = 5.0
    additional_charge: float = 0.0
    is_active: bool = True

class PricingRuleUpdate(BaseModel):
    price_per_page: Optional[float] = None
    min_order_price: Optional[float] = None
    additional_charge: Optional[float] = None
    is_active: Optional[bool] = None

class PricingRuleOut(BaseModel):
    id: int
    paper_size: str
    is_color: bool
    is_double_sided: bool
    price_per_page: float
    min_order_price: float
    additional_charge: float
    is_active: bool
    updated_at: datetime

    class Config:
        from_attributes = True
