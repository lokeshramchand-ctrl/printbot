from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime

class RazorpayWebhookPayload(BaseModel):
    entity: str
    account_id: str
    event: str
    contains: List[str] = []
    payload: Dict[str, Any]
    created_at: int

class PaymentOut(BaseModel):
    id: int
    order_id: str
    razorpay_order_id: Optional[str] = None
    razorpay_payment_id: Optional[str] = None
    razorpay_payment_link_url: Optional[str] = None
    amount: float
    currency: str
    status: str
    method: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
