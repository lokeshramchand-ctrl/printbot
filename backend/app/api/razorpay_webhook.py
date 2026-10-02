from fastapi import APIRouter, Depends, Request, Header, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime
from app.database import get_db
from app.config import settings
from app.models.order import Order
from app.models.payment import Payment
from app.models.history import OrderStatusHistory
from app.models.webhook_event import WebhookEvent
from app.services.razorpay_service import razorpay_service
from app.services.whatsapp_service import whatsapp_service
from app.services.print_service import print_service
from app.services.websocket_service import manager as websocket_manager
import logging

logger = logging.getLogger("razorpay_webhook")

router = APIRouter(prefix="/webhooks/razorpay", tags=["Razorpay Webhook"])

@router.post("")
async def receive_razorpay_webhook(
    request: Request,
    x_razorpay_signature: str = Header(None),
    db: Session = Depends(get_db)
):
    """
    Razorpay Webhook Receiver.
    Processes server-side payment confirmation securely.
    """
    body_bytes = await request.body()
    
    # 1. Verify Webhook Signature (if production keys are configured)
    is_test_mode = (settings.RAZORPAY_KEY_ID == "rzp_test_key_id")
    if not is_test_mode and x_razorpay_signature:
        valid_sig = razorpay_service.verify_webhook_signature(body_bytes, x_razorpay_signature)
        if not valid_sig:
            logger.error("Invalid Razorpay webhook signature!")
            raise HTTPException(status_code=400, detail="Invalid webhook signature")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_type = payload.get("event")
    event_id = payload.get("event_id") or payload.get("payload", {}).get("payment", {}).get("entity", {}).get("id") or str(payload.get("created_at"))

    logger.info(f"Received Razorpay Webhook Event: {event_type} (Event ID: {event_id})")

    # 2. Idempotency Check
    existing_event = db.query(WebhookEvent).filter(WebhookEvent.event_id == event_id).first()
    if existing_event and existing_event.processed:
        logger.info(f"Razorpay webhook event {event_id} already processed. Skipping.")
        return {"status": "already_processed"}

    # Store event log
    if not existing_event:
        event_record = WebhookEvent(
            event_id=event_id,
            provider="RAZORPAY",
            event_type=event_type or "unknown",
            payload=payload,
            processed=False
        )
        db.add(event_record)
        db.commit()
    else:
        event_record = existing_event

    # 3. Handle payment success events
    if event_type in ("payment.captured", "payment_link.paid", "order.paid"):
        payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
        plink_entity = payload.get("payload", {}).get("payment_link", {}).get("entity", {})

        order_id = (
            payment_entity.get("notes", {}).get("order_id") or
            plink_entity.get("reference_id") or
            plink_entity.get("notes", {}).get("order_id")
        )
        
        razorpay_payment_id = payment_entity.get("id")
        razorpay_order_id = payment_entity.get("order_id")
        amount_paise = payment_entity.get("amount") or plink_entity.get("amount") or 0
        amount_inr = amount_paise / 100.0
        method = payment_entity.get("method", "upi")

        if order_id:
            order = db.query(Order).filter(Order.id == order_id).first()
            if order:
                # Update Order payment & print status
                if order.payment_status != "PAID":
                    order.payment_status = "PAID"
                    order.current_state = "PAID"

                    # Record payment in DB
                    payment_rec = Payment(
                        order_id=order.id,
                        razorpay_order_id=razorpay_order_id,
                        razorpay_payment_id=razorpay_payment_id,
                        amount=amount_inr,
                        currency="INR",
                        status="CAPTURED",
                        method=method,
                        raw_payload=payload
                    )
                    db.add(payment_rec)

                    history = OrderStatusHistory(
                        order_id=order.id,
                        from_status="PAYMENT_PENDING",
                        to_status="PAID",
                        trigger_source="WEBHOOK",
                        notes=f"Payment of ₹{amount_inr:.2f} confirmed via Razorpay ({razorpay_payment_id})"
                    )
                    db.add(history)
                    db.commit()

                    # Send WhatsApp Payment Confirmation to Customer
                    if order.customer:
                        confirm_msg = (
                            f"✅ *Payment received!*\n\n"
                            f"Order *#{order.id}* has been confirmed.\n\n"
                            "🖨️ Your document is now in the print queue.\n"
                            "We will notify you when printing begins and when it is ready."
                        )
                        await whatsapp_service.send_text_message(order.customer.whatsapp_number, confirm_msg)

                    # Release document into print queue
                    print_job = print_service.submit_job(db, order)
                    
                    # Notify WhatsApp printing started
                    if order.customer:
                        await whatsapp_service.send_text_message(
                            order.customer.whatsapp_number,
                            f"🖨️ *Order #{order.id} is now printing...*"
                        )

                    # Execute print job
                    print_service.execute_print_job(db, print_job.id)

                    # Send WhatsApp notification when complete
                    if order.customer and order.current_state == "COMPLETED":
                        ready_msg = (
                            f"✅ *PRINT COMPLETE*\n\n"
                            f"Order *#{order.id}* is ready for pickup!\n\n"
                            f"📍 *Pickup Location:* {settings.PICKUP_ADDRESS}\n\n"
                            "Thank you for using PrintBot! 🙏"
                        )
                        await whatsapp_service.send_text_message(order.customer.whatsapp_number, ready_msg)

                    # Broadcast real-time update to Admin UI
                    await websocket_manager.broadcast_event(
                        "order_updated",
                        {"order_id": order.id, "status": order.current_state, "payment_status": "PAID"}
                    )

    # Mark webhook event as processed
    event_record.processed = True
    db.commit()

    return {"status": "success"}
