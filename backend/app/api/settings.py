from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from app.config import settings
from app.models.admin import Admin
from app.api.auth import get_current_admin

router = APIRouter(prefix="/api/settings", tags=["Settings"])

class SettingsUpdate(BaseModel):
    business_name: Optional[str] = None
    business_phone: Optional[str] = None
    pickup_address: Optional[str] = None
    file_retention_days: Optional[int] = None
    use_virtual_printer: Optional[bool] = None
    cover_sheet_enabled: Optional[bool] = None

@router.get("")
def get_system_settings(current_admin: Admin = Depends(get_current_admin)):
    """Fetch current system and business settings."""
    return {
        "business_name": settings.BUSINESS_NAME,
        "business_phone": settings.BUSINESS_PHONE,
        "pickup_address": settings.PICKUP_ADDRESS,
        "file_retention_days": settings.FILE_RETENTION_DAYS,
        "max_file_size_mb": settings.MAX_FILE_SIZE_MB,
        "use_virtual_printer": settings.USE_VIRTUAL_PRINTER,
        "cover_sheet_enabled": settings.COVER_SHEET_ENABLED,
        "cups_host": settings.CUPS_HOST,
        "whatsapp_phone_number_id": settings.WHATSAPP_PHONE_NUMBER_ID,
        "telegram_bot_token": settings.TELEGRAM_BOT_TOKEN[:10] + "..." if settings.TELEGRAM_BOT_TOKEN else "Not Configured",
        "payment_mode": settings.PAYMENT_MODE,
        "razorpay_key_id": settings.RAZORPAY_KEY_ID if settings.PAYMENT_MODE == "razorpay" else "",
        "environment": settings.ENV
    }

@router.put("")
def update_system_settings(
    req: SettingsUpdate,
    current_admin: Admin = Depends(get_current_admin)
):
    """Update non-sensitive runtime business settings."""
    if req.business_name is not None:
        settings.BUSINESS_NAME = req.business_name
    if req.business_phone is not None:
        settings.BUSINESS_PHONE = req.business_phone
    if req.pickup_address is not None:
        settings.PICKUP_ADDRESS = req.pickup_address
    if req.file_retention_days is not None:
        settings.FILE_RETENTION_DAYS = req.file_retention_days
    if req.use_virtual_printer is not None:
        settings.USE_VIRTUAL_PRINTER = req.use_virtual_printer
    if req.cover_sheet_enabled is not None:
        settings.COVER_SHEET_ENABLED = req.cover_sheet_enabled

    return {
        "status": "success",
        "message": "System settings updated successfully",
        "settings": {
            "business_name": settings.BUSINESS_NAME,
            "business_phone": settings.BUSINESS_PHONE,
            "pickup_address": settings.PICKUP_ADDRESS,
            "file_retention_days": settings.FILE_RETENTION_DAYS,
            "use_virtual_printer": settings.USE_VIRTUAL_PRINTER,
            "cover_sheet_enabled": settings.COVER_SHEET_ENABLED
        }
    }
