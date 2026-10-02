from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from typing import Dict, Any, List
from app.database import get_db
from app.models.admin import Admin
from app.models.order import Order
from app.models.printer import Printer
from app.models.print_job import PrintJob
from app.api.auth import get_current_admin

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])

@router.get("/dashboard")
def get_dashboard_stats(
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
) -> Dict[str, Any]:
    """Provides high-level real-time KPI metrics and revenue analytics for the Admin Dashboard."""
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    # Today's metrics
    todays_orders_count = db.query(Order).filter(Order.created_at >= today_start).count()
    
    todays_revenue_res = db.query(func.sum(Order.total_amount)).filter(
        Order.created_at >= today_start,
        Order.payment_status == "PAID"
    ).scalar()
    todays_revenue = todays_revenue_res or 0.0

    # Queue & Order Status counts
    pending_payments_count = db.query(Order).filter(Order.payment_status == "PENDING").count()
    print_queue_count = db.query(PrintJob).filter(PrintJob.status == "QUEUED").count()
    currently_printing_count = db.query(PrintJob).filter(PrintJob.status == "PRINTING").count()
    completed_orders_count = db.query(Order).filter(Order.current_state == "COMPLETED").count()
    failed_orders_count = db.query(Order).filter(Order.current_state.in_(["PROCESSING_FAILED", "PAYMENT_FAILED", "PRINT_FAILED"])).count()

    # Total pages Breakdown
    bw_pages_res = db.query(func.sum(Order.total_pages * Order.copies)).filter(
        Order.payment_status == "PAID",
        Order.color_mode == "BW"
    ).scalar()
    bw_pages = bw_pages_res or 0

    color_pages_res = db.query(func.sum(Order.total_pages * Order.copies)).filter(
        Order.payment_status == "PAID",
        Order.color_mode == "Color"
    ).scalar()
    color_pages = color_pages_res or 0

    total_pages = bw_pages + color_pages

    # 7-Day Revenue Trend Chart
    revenue_chart: List[Dict[str, Any]] = []
    for i in range(6, -1, -1):
        day_date = datetime.utcnow().date() - timedelta(days=i)
        day_start = datetime.combine(day_date, datetime.min.time())
        day_end = datetime.combine(day_date, datetime.max.time())
        
        day_rev = db.query(func.sum(Order.total_amount)).filter(
            Order.created_at >= day_start,
            Order.created_at <= day_end,
            Order.payment_status == "PAID"
        ).scalar() or 0.0

        day_orders = db.query(Order).filter(
            Order.created_at >= day_start,
            Order.created_at <= day_end
        ).count()

        revenue_chart.append({
            "date": day_date.strftime("%b %d"),
            "revenue": round(day_rev, 2),
            "orders": day_orders
        })

    # Printer status counts
    online_printers = db.query(Printer).filter(Printer.is_online == True).count()
    total_printers = db.query(Printer).count()

    return {
        "kpis": {
            "todays_orders": todays_orders_count,
            "todays_revenue": round(todays_revenue, 2),
            "pending_payments": pending_payments_count,
            "queue_length": print_queue_count,
            "currently_printing": currently_printing_count,
            "completed_orders": completed_orders_count,
            "failed_orders": failed_orders_count,
            "total_pages": total_pages,
            "bw_pages": bw_pages,
            "color_pages": color_pages,
            "online_printers": online_printers,
            "total_printers": total_printers
        },
        "revenue_chart": revenue_chart
    }
