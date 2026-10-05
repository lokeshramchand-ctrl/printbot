from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional
import os
from app.database import get_db
from app.models.admin import Admin
from app.models.order import Order
from app.models.history import OrderStatusHistory
from app.schemas.order import OrderOut, OrderDetailOut, OrderActionRequest
from app.api.auth import get_current_admin
from app.services.print_service import print_service
from app.config import settings
from app.models.payment import Payment
from app.services import messenger, payment_service
from app.services.razorpay_service import razorpay_service
from app.services.websocket_service import manager as websocket_manager

router = APIRouter(prefix="/api/orders", tags=["Orders"])

@router.get("", response_model=List[OrderOut])
def get_orders(
    status_filter: Optional[str] = Query(None, alias="status"),
    q: Optional[str] = Query(None, description="Search by Order ID, File Name or WhatsApp Number"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    """Retrieve list of print orders with search and status filter."""
    query = db.query(Order)
    
    if status_filter:
        query = query.filter(Order.current_state == status_filter.upper())
        
    if q:
        search_pattern = f"%{q}%"
        query = query.join(Order.customer).filter(
            (Order.id.ilike(search_pattern)) |
            (Order.original_file_name.ilike(search_pattern)) |
            (Order.customer.property.mapper.class_.whatsapp_number.ilike(search_pattern))
        )

    # Active-queue views (QUEUED/PRINTING) must reflect true FIFO order —
    # the order jobs were actually submitted, not most-recent-first — so
    # staff working the physical queue print in the same sequence the
    # system committed. Everywhere else, most-recent-first is the more
    # useful browsing order for an admin scanning recent activity.
    if status_filter and status_filter.upper() in ("QUEUED", "PRINTING"):
        orders = query.order_by(Order.created_at.asc()).offset(offset).limit(limit).all()
    else:
        orders = query.order_by(Order.created_at.desc()).offset(offset).limit(limit).all()
    return orders

@router.get("/{order_id}", response_model=OrderDetailOut)
def get_order_detail(
    order_id: str,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    """Get detailed order breakdown."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@router.get("/{order_id}/download")
def download_order_file(
    order_id: str,
    file_type: str = Query("printable", description="printable or original"),
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    """Secure endpoint for admins to view/download order document files."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    target_path = order.printable_pdf_path if file_type == "printable" else order.stored_file_path
    if not target_path or not os.path.exists(target_path):
        raise HTTPException(status_code=404, detail="Requested file not found on server storage")

    filename = os.path.basename(target_path)
    return FileResponse(path=target_path, filename=filename, media_type="application/pdf" if target_path.endswith(".pdf") else "application/octet-stream")

@router.post("/{order_id}/action")
async def execute_order_action(
    order_id: str,
    req: OrderActionRequest,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    """Execute manual admin operations (PRINT, RETRY, CANCEL, REFUND)."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    action = req.action.upper()
    notes = req.notes or f"Manual admin action: {action}"

    if action in ("PRINT", "RETRY"):
        if order.payment_status != "PAID":
            raise HTTPException(status_code=400, detail="Order is not paid; refusing to print it.")
        if order.current_state in ("CANCELLED", "REFUNDED"):
            raise HTTPException(status_code=400, detail=f"Order is {order.current_state}; cannot print.")
        # Re-submit to queue and print
        print_job = print_service.submit_job(db, order, target_printer_id=req.printer_id)
        success = print_service.execute_print_job(db, print_job.id)

        if success and order.customer:
            pickup_note = (f" Pickup code: *{order.pickup_code}*." if order.pickup_code else
                           (f" Show reference *{order.print_serial}* at pickup." if order.print_serial else ""))
            await messenger.send_message(
                order.customer,
                f"✅ *Order #{order.id} update:* Your document has been printed and is ready for pickup!{pickup_note}"
            )

        await websocket_manager.broadcast_event("order_updated", {"order_id": order.id, "status": order.current_state})
        return {"status": "success", "new_state": order.current_state, "print_success": success}

    elif action == "CANCEL":
        previous = order.current_state
        if previous in ("COMPLETED", "CANCELLED"):
            raise HTTPException(status_code=400, detail=f"Order is already {previous}.")
        if order.payment_status == "PENDING":
            await payment_service.cancel_order(db, order, source="ADMIN", notes=notes)
        else:
            order.current_state = "CANCELLED"
            order.print_status = "CANCELLED"
            db.add(OrderStatusHistory(order_id=order.id, from_status=previous, to_status="CANCELLED",
                                      trigger_source="ADMIN", notes=notes))
            db.commit()

        customer = order.customer
        if customer:
            if customer.active_order_id == order.id:
                customer.active_order_id = None
                customer.bot_state = "IDLE"
                db.commit()
            await messenger.send_message(customer, f"❌ Order #{order.id} has been cancelled by the shop admin.")

        await websocket_manager.broadcast_event("order_updated", {"order_id": order.id, "status": "CANCELLED"})
        return {"status": "success", "new_state": "CANCELLED"}

    elif action == "REFUND":
        if order.payment_status != "PAID":
            raise HTTPException(status_code=400, detail="Only paid orders can be refunded.")
        refund_note = notes
        captured = db.query(Payment).filter(Payment.order_id == order.id, Payment.status == "CAPTURED").first()
        if captured and captured.razorpay_payment_id and settings.PAYMENT_MODE == "razorpay":
            result = await razorpay_service.refund_payment(captured.razorpay_payment_id)
            if not result.get("success"):
                raise HTTPException(status_code=502, detail=f"Razorpay refund failed: {result.get('error')}")
            captured.status = "REFUNDED"
            refund_note = f"{notes} (Razorpay refund {result.get('refund_id')})"
        elif captured:
            captured.status = "REFUNDED"
        order.payment_status = "REFUNDED"
        db.add(OrderStatusHistory(order_id=order.id, from_status="PAID", to_status="REFUNDED",
                                  trigger_source="ADMIN", notes=refund_note))
        db.commit()

        if order.customer:
            await messenger.send_message(
                order.customer, f"💸 Payment for Order #{order.id} (₹{order.total_amount:.2f}) has been refunded."
            )

        await websocket_manager.broadcast_event("order_updated", {"order_id": order.id, "payment_status": "REFUNDED"})
        return {"status": "success", "payment_status": "REFUNDED"}

    else:
        raise HTTPException(status_code=400, detail=f"Unsupported action: {req.action}")
