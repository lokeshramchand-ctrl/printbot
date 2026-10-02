"""Payment orchestration shared by demo mode and Razorpay.

One pipeline, two triggers:

* demo mode     -> customer taps "Pay (Demo)" in the bot  -> ``confirm_payment``
* razorpay mode -> signed Razorpay webhook                  -> ``confirm_payment``

``confirm_payment`` is idempotent and atomic (a single conditional update
flips PAYMENT_PENDING -> PAID), so a double-tap, a webhook retry or a webhook
racing a button press can never queue or print an order twice.
"""
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from app.config import settings
from app.models.customer import Customer
from app.models.history import OrderStatusHistory
from app.models.order import Order
from app.models.payment import Payment
from app.services import messenger
from app.services.print_service import print_service
from app.services.razorpay_service import razorpay_service
from app.services.websocket_service import manager as websocket_manager

logger = logging.getLogger("payment_service")

PAYABLE_STATES = ("PAYMENT_PENDING",)


def is_demo_mode() -> bool:
    return settings.PAYMENT_MODE == "demo"


def _history(db, order_id: str, from_status: str, to_status: str, source: str, notes: str) -> None:
    db.add(OrderStatusHistory(order_id=order_id, from_status=from_status, to_status=to_status,
                              trigger_source=source, notes=notes))


def _pending_payment(db, order_id: str) -> Optional[Payment]:
    return db.query(Payment).filter(Payment.order_id == order_id, Payment.status == "CREATED").first()


async def create_checkout(db, order: Order, customer: Customer, description: str) -> Dict[str, Any]:
    """Prepare payment for a freshly created order.

    Returns ``{"success": True, "payment_url": <str|None>}``; a ``None`` URL
    means demo mode (the bot shows a Pay (Demo) button instead of a link).
    """
    if is_demo_mode():
        db.add(Payment(order_id=order.id, amount=order.total_amount, currency="INR",
                       status="CREATED", method="demo"))
        db.commit()
        return {"success": True, "payment_url": None, "mode": "demo"}

    contact = customer.whatsapp_number if customer.channel == "WHATSAPP" else None
    res = await razorpay_service.create_payment_link(order.id, order.total_amount, contact, description)
    if not res.get("success"):
        return res
    db.add(Payment(order_id=order.id, amount=order.total_amount, currency="INR", status="CREATED",
                   razorpay_payment_link_id=res.get("payment_link_id"),
                   razorpay_payment_link_url=res["payment_url"]))
    db.commit()
    return {**res, "mode": "razorpay"}


async def confirm_payment(
    db,
    order_id: str,
    *,
    source: str,
    method: str = "demo",
    amount_inr: Optional[float] = None,
    razorpay_payment_id: Optional[str] = None,
    razorpay_order_id: Optional[str] = None,
    raw_payload: Optional[dict] = None,
) -> Dict[str, Any]:
    """Mark an order PAID exactly once, then queue + print it and notify everyone.

    Returns ``{"status": "paid" | "already_processed" | "not_payable" | "not_found"}``.
    """
    now = datetime.utcnow()
    claimed = db.database.orders.find_one_and_update(
        {"id": order_id, "payment_status": "PENDING", "current_state": {"$in": list(PAYABLE_STATES)}},
        {"$set": {"payment_status": "PAID", "current_state": "PAID", "updated_at": now}},
    )
    if claimed is None:
        order = db.query(Order).filter(Order.id == order_id).first()
        if order is None:
            return {"status": "not_found"}
        if order.payment_status == "PAID":
            return {"status": "already_processed"}
        return {"status": "not_payable", "state": order.current_state}

    order = db.query(Order).filter(Order.id == order_id).first()
    customer = order.customer
    paid_amount = amount_inr if amount_inr is not None else order.total_amount

    payment = _pending_payment(db, order.id)
    if payment is None:
        payment = Payment(order_id=order.id, currency="INR")
        db.add(payment)
    payment.amount = paid_amount
    payment.status = "CAPTURED"
    payment.method = method
    payment.razorpay_payment_id = razorpay_payment_id or payment.razorpay_payment_id
    payment.razorpay_order_id = razorpay_order_id or payment.razorpay_order_id
    payment.raw_payload = raw_payload
    _history(db, order.id, "PAYMENT_PENDING", "PAID", source,
             f"Payment of ₹{paid_amount:.2f} confirmed via {method}"
             + (f" ({razorpay_payment_id})" if razorpay_payment_id else ""))

    if customer:
        customer.bot_state = "IDLE"
        customer.active_order_id = None
        customer.state_data = {}
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(customer, "state_data")
    db.commit()

    await websocket_manager.broadcast_event(
        "order_updated", {"order_id": order.id, "status": "PAID", "payment_status": "PAID"})

    if customer:
        await messenger.send_message(
            customer,
            f"✅ *Payment received!*\n\nOrder *#{order.id}* is confirmed and added to the print queue.\n"
            "We'll message you when it's ready.")

    job = print_service.submit_job(db, order)
    print_service.execute_print_job(db, job.id)
    db.refresh(order)

    if order.current_state == "COMPLETED" and customer:
        serial = f"\n🔖 Reference: *{order.print_serial}*" if order.print_serial else ""
        await messenger.send_message(
            customer,
            f"🖨️ *Print complete!*\n\nOrder *#{order.id}* is ready for pickup.{serial}\n\n"
            f"📍 {settings.PICKUP_ADDRESS}\n\nThank you for using {settings.BUSINESS_NAME}! 🙏")
    elif customer:
        await messenger.send_message(
            customer,
            f"⚠️ Order *#{order.id}* is paid but printing hit a problem. "
            f"The shop has been alerted and will sort it out. Call {settings.BUSINESS_PHONE} if urgent.")

    await websocket_manager.broadcast_event(
        "order_updated", {"order_id": order.id, "status": order.current_state, "payment_status": "PAID"})
    return {"status": "paid", "order_state": order.current_state}


async def cancel_order(db, order: Order, *, source: str, notes: str = "Cancelled") -> bool:
    """Cancel an unpaid order and its Razorpay link. Paid orders must be refunded instead."""
    claimed = db.database.orders.find_one_and_update(
        {"id": order.id, "payment_status": "PENDING", "current_state": {"$in": list(PAYABLE_STATES)}},
        {"$set": {"current_state": "CANCELLED", "print_status": "CANCELLED", "updated_at": datetime.utcnow()}},
    )
    if claimed is None:
        return False
    db.refresh(order)

    payment = _pending_payment(db, order.id)
    if payment is not None:
        payment.status = "CANCELLED"
        if payment.razorpay_payment_link_id:
            await razorpay_service.cancel_payment_link(payment.razorpay_payment_link_id)
    _history(db, order.id, "PAYMENT_PENDING", "CANCELLED", source, notes)
    db.commit()
    await websocket_manager.broadcast_event("order_updated", {"order_id": order.id, "status": "CANCELLED"})
    return True
