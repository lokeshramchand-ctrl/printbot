from app.models.admin import Admin
from app.models.customer import Customer
from app.models.order import Order
from app.models.uploaded_file import UploadedFile
from app.models.payment import Payment
from app.models.printer import Printer
from app.models.print_job import PrintJob
from app.models.pricing import PricingRule
from app.models.message import WhatsAppMessage
from app.models.history import OrderStatusHistory
from app.models.webhook_event import WebhookEvent
from app.models.serial_counter import SerialCounter

MODEL_BY_TABLE = {
    Admin.__tablename__: Admin,
    Customer.__tablename__: Customer,
    Order.__tablename__: Order,
    UploadedFile.__tablename__: UploadedFile,
    Payment.__tablename__: Payment,
    Printer.__tablename__: Printer,
    PrintJob.__tablename__: PrintJob,
    PricingRule.__tablename__: PricingRule,
    WhatsAppMessage.__tablename__: WhatsAppMessage,
    OrderStatusHistory.__tablename__: OrderStatusHistory,
    WebhookEvent.__tablename__: WebhookEvent,
    SerialCounter.__tablename__: SerialCounter,
}

__all__ = [
    "Admin",
    "Customer",
    "Order",
    "UploadedFile",
    "Payment",
    "Printer",
    "PrintJob",
    "PricingRule",
    "WhatsAppMessage",
    "OrderStatusHistory",
    "WebhookEvent",
    "SerialCounter",
    "MODEL_BY_TABLE",
]
