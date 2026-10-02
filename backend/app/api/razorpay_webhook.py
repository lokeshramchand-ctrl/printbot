import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pymongo.errors import DuplicateKeyError
from sqlalchemy.orm import Session

from app.config import razorpay_configured, settings
from app.database import get_db
from app.models.history import OrderStatusHistory
from app.models.order import Order
from app.models.payment import Payment
from app.models.webhook_event import WebhookEvent
from app.services import messenger, payment_service
from app.services.razorpay_service import razorpay_service
from app.services.websocket_service import manager as websocket_manager

logger = logging.getLogger("razorpay_webhook")

router = APIRouter(prefix="/webhooks/razorpay", tags=["Razorpay Webhook"])

PAID_EVENTS = ("payment_link.paid", "payment.captured", "order.paid")


def _entities(payload: Dict[str, Any]) -> tuple[dict, dict]:
    body = payload.get("payload", {})
    return body.get("payment", {}).get("entity", {}) or {}, body.get("payment_link", {}).get("entity", {}) or {}


def _order_id_from(payment: dict, link: dict) -> Optional[str]:
    return (
        (payment.get("notes") or {}).get("order_id")
        or link.get("reference_id")
        or (link.get("notes") or {}).get("order_id")
    )


@router.post("")
async def receive_razorpay_webhook(
    request: Request,
    x_razorpay_signature: Optional[str] = Header(None),
    x_razorpay_event_id: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """Razorpay webhook receiver (``PAYMENT_MODE=razorpay`` only).

    The HMAC signature is ALWAYS verified against the raw body. A missing or
    wrong signature is rejected - there is no test-mode bypass.
    """
    if settings.PAYMENT_MODE != "razorpay" or not razorpay_configured():
        raise HTTPException(status_code=404, detail="Razorpay payments are not enabled")

    body_bytes = await request.body()
    if not razorpay_service.verify_webhook_signature(body_bytes, x_razorpay_signature):
        logger.error("Rejected Razorpay webhook: missing/invalid signature")
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_type = payload.get("event") or "unknown"
    payment_entity, link_entity = _entities(payload)
    event_id = (
        x_razorpay_event_id
        or payload.get("event_id")
        or f"{event_type}:{payment_entity.get('id') or link_entity.get('id') or payload.get('created_at')}"
    )
    logger.info(f"Razorpay webhook {event_type} ({event_id})")

    # Idempotency: the unique index on event_id makes a concurrent duplicate fail fast.
    existing = db.query(WebhookEvent).filter(WebhookEvent.event_id == event_id).first()
    if existing and existing.processed:
        return {"status": "already_processed"}
    if existing:
        record = existing
    else:
        record = WebhookEvent(event_id=event_id, provider="RAZORPAY", event_type=event_type,
                              payload=payload, processed=False)
        try:
            db.add(record)
            db.commit()
        except DuplicateKeyError:
            return {"status": "already_processed"}

    order_id = _order_id_from(payment_entity, link_entity)
    order = db.query(Order).filter(Order.id == order_id).first() if order_id else None
    result = "ignored"

    if event_type in PAID_EVENTS and order is not None:
        result = await _handle_paid(db, order, payment_entity, link_entity, payload, record)
    elif event_type in ("payment_link.expired", "payment_link.cancelled") and order is not None:
        result = await _handle_link_closed(db, order, event_type)
    elif event_type == "payment.failed" and order is not None:
        await _notify_failed(order)
        result = "failed_notified"

    record.processed = True
    db.commit()
    return {"status": "success", "result": result}


async def _handle_paid(db, order: Order, payment: dict, link: dict, payload: dict, record: WebhookEvent) -> str:
    amount_paise = payment.get("amount") or link.get("amount") or 0
    currency = payment.get("currency") or link.get("currency") or "INR"
    expected_paise = int(round(order.total_amount * 100))

    # Never release a print job for a short payment or a payment against another order's link.
    if amount_paise != expected_paise or currency != "INR":
        note = f"Payment mismatch: got {amount_paise} {currency} paise, expected {expected_paise} INR paise"
        logger.error(f"{order.id}: {note}")
        record.error_message = note[:500]
        db.add(OrderStatusHistory(order_id=order.id, from_status=order.current_state, to_status=order.current_state,
                                  trigger_source="WEBHOOK", notes=note))
        db.commit()
        return "amount_mismatch"

    stored = db.query(Payment).filter(Payment.order_id == order.id, Payment.status == "CREATED").first()
    link_id = link.get("id")
    if stored and stored.razorpay_payment_link_id and link_id and stored.razorpay_payment_link_id != link_id:
        record.error_message = "Payment link does not belong to this order"
        db.commit()
        return "link_mismatch"

    if order.current_state == "CANCELLED":
        # Money arrived for an order the customer/admin already cancelled: keep the evidence, flag a refund.
        db.add(Payment(order_id=order.id, amount=amount_paise / 100.0, currency="INR", status="CAPTURED",
                       method=payment.get("method"), razorpay_payment_id=payment.get("id"), raw_payload=payload))
        db.add(OrderStatusHistory(order_id=order.id, from_status="CANCELLED", to_status="CANCELLED",
                                  trigger_source="WEBHOOK",
                                  notes=f"REFUND REQUIRED: paid after cancellation ({payment.get('id')})"))
        db.commit()
        await websocket_manager.broadcast_event("order_updated", {"order_id": order.id, "status": "CANCELLED",
                                                                    "refund_required": True})
        return "paid_after_cancel"

    outcome = await payment_service.confirm_payment(
        db, order.id, source="WEBHOOK", method=payment.get("method") or "razorpay",
        amount_inr=amount_paise / 100.0, razorpay_payment_id=payment.get("id"),
        razorpay_order_id=payment.get("order_id"), raw_payload=payload)
    return outcome["status"]


async def _handle_link_closed(db, order: Order, event_type: str) -> str:
    if order.current_state != "PAYMENT_PENDING":
        return "ignored"
    if await payment_service.cancel_order(db, order, source="WEBHOOK", notes=f"Payment link {event_type.split('.')[-1]}"):
        if order.customer:
            customer = order.customer
            if customer.active_order_id == order.id:
                customer.active_order_id = None
                customer.bot_state = "IDLE"
                db.commit()
            await messenger.send_message(
                customer, f"⌛ The payment link for order *#{order.id}* has expired and the order was cancelled. "
                          "Send your document again to start a new one.")
        return "cancelled"
    return "ignored"


async def _notify_failed(order: Order) -> None:
    if order.customer and order.current_state == "PAYMENT_PENDING":
        await messenger.send_message(
            order.customer, f"⚠️ Your payment for order *#{order.id}* didn't go through. "
                            "You can retry with the same payment link.")
