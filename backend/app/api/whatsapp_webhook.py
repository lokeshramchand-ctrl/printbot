import hashlib
import hmac
from fastapi import APIRouter, Depends, Request, Response, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.config import settings
from app.services.bot_state_machine import bot_state_machine
from app.services.websocket_service import manager as websocket_manager
import logging

logger = logging.getLogger("whatsapp_webhook")

router = APIRouter(prefix="/webhooks/whatsapp", tags=["WhatsApp Webhook"])

@router.get("")
def verify_whatsapp_webhook(request: Request):
    """WhatsApp Cloud API Webhook Verification Endpoint."""
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == settings.WHATSAPP_VERIFY_TOKEN:
        logger.info("WhatsApp webhook verified successfully.")
        return Response(content=challenge, media_type="text/plain")
    else:
        logger.warning(f"WhatsApp webhook verification failed with token: {token}")
        raise HTTPException(status_code=403, detail="Verification token mismatch")

@router.post("")
async def receive_whatsapp_webhook(request: Request, db: Session = Depends(get_db)):
    """Inbound WhatsApp Webhook Event Receiver."""
    raw = await request.body()
    if settings.WHATSAPP_APP_SECRET:
        expected = "sha256=" + hmac.new(settings.WHATSAPP_APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, request.headers.get("X-Hub-Signature-256", "")):
            raise HTTPException(status_code=403, detail="Invalid WhatsApp signature")
    try:
        body = await request.json()
        logger.info("Received WhatsApp webhook event")
        
        # Process message in bot state machine
        await bot_state_machine.handle_inbound_message(db, body)

        # Notify admin UI via WebSocket
        await websocket_manager.broadcast_event("whatsapp_message_received", {"timestamp": "now"})

        return {"status": "ok"}
    except Exception as e:
        logger.exception(f"Error handling WhatsApp webhook payload: {str(e)}")
        return {"status": "error", "detail": str(e)}
