from fastapi import APIRouter, Depends, Request, Query, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.bot_state_machine import bot_state_machine
from app.services.telegram_service import telegram_service
from app.services.websocket_service import manager as websocket_manager
import logging

logger = logging.getLogger("telegram_webhook")

router = APIRouter(prefix="/webhooks/telegram", tags=["Telegram Webhook"])

@router.post("")
async def receive_telegram_webhook(request: Request, db: Session = Depends(get_db)):
    """Inbound Telegram Webhook Receiver."""
    try:
        body = await request.json()
        logger.info(f"Received Telegram webhook update: {body}")
        
        await bot_state_machine.handle_telegram_update(db, body)

        # Notify admin UI via WebSocket
        await websocket_manager.broadcast_event("telegram_message_received", {"timestamp": "now"})

        return {"status": "ok"}
    except Exception as e:
        logger.exception(f"Error handling Telegram webhook payload: {str(e)}")
        return {"status": "error", "detail": str(e)}

@router.get("/setup")
async def setup_telegram_webhook(url: str = Query(..., description="Public HTTPS Webhook URL")):
    """Register server endpoint with Telegram Bot API."""
    target_url = f"{url.rstrip('/')}/webhooks/telegram"
    success = await telegram_service.set_webhook(target_url)
    if success:
        return {"status": "success", "message": f"Telegram Webhook registered at {target_url}"}
    else:
        raise HTTPException(status_code=400, detail="Failed to register Telegram Webhook")
