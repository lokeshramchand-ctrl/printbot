from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Any
from app.database import get_db
from app.models.admin import Admin
from app.models.customer import Customer
from app.models.order import Order
from app.api.auth import get_current_admin

router = APIRouter(prefix="/api/customers", tags=["Customers"])

@router.get("")
def get_customers(
    q: str = Query(None),
    limit: int = Query(50),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
) -> List[Dict[str, Any]]:
    """List customer records with multi-channel analytics."""
    query = db.query(Customer)
    if q:
        search_pat = f"%{q}%"
        query = query.filter(
            (Customer.whatsapp_number.ilike(search_pat)) |
            (Customer.telegram_chat_id.ilike(search_pat)) |
            (Customer.display_name.ilike(search_pat))
        )
    
    customers = query.order_by(Customer.updated_at.desc()).offset(offset).limit(limit).all()
    
    result = []
    for c in customers:
        order_count = db.query(Order).filter(Order.customer_id == c.id).count()
        total_spent = db.query(func.sum(Order.total_amount)).filter(
            Order.customer_id == c.id,
            Order.payment_status == "PAID"
        ).scalar() or 0.0
        
        last_order = db.query(Order).filter(Order.customer_id == c.id).order_by(Order.created_at.desc()).first()

        result.append({
            "id": c.id,
            "channel": c.channel,
            "whatsapp_number": c.whatsapp_number,
            "telegram_chat_id": c.telegram_chat_id,
            "display_name": c.display_name or "Customer",
            "bot_state": c.bot_state,
            "order_count": order_count,
            "total_spent": round(total_spent, 2),
            "last_order_id": last_order.id if last_order else None,
            "last_order_date": last_order.created_at.isoformat() if last_order else None,
            "created_at": c.created_at.isoformat()
        })

    return result
