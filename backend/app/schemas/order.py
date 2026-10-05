from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class CustomerBrief(BaseModel):
    id: int
    channel: str = "WHATSAPP"
    whatsapp_number: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    display_name: Optional[str] = None

    class Config:
        from_attributes = True

class OrderOut(BaseModel):
    id: str
    customer_id: int
    channel: str = "WHATSAPP"
    customer: Optional[CustomerBrief] = None
    original_file_name: Optional[str] = None
    file_type: Optional[str] = None
    file_size_bytes: int = 0
    total_pages: int
    copies: int
    paper_size: str
    color_mode: str
    sides: str
    pages_to_print: str
    total_amount: float
    payment_status: str
    current_state: str
    print_status: str
    print_serial: Optional[str] = None
    pickup_code: Optional[str] = None
    failure_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class OrderHistoryOut(BaseModel):
    id: int
    from_status: Optional[str] = None
    to_status: str
    trigger_source: str
    notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class PaymentBriefOut(BaseModel):
    id: int
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

class OrderDetailOut(OrderOut):
    rate_per_page: float
    subtotal_amount: float
    additional_charges: float
    stored_file_path: Optional[str] = None
    printable_pdf_path: Optional[str] = None
    history: List[OrderHistoryOut] = []
    payments: List[PaymentBriefOut] = []

    class Config:
        from_attributes = True

class OrderActionRequest(BaseModel):
    action: str  # PRINT, RETRY, CANCEL, REFUND
    printer_id: Optional[int] = None
    notes: Optional[str] = None
