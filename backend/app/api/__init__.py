from app.api.auth import router as auth_router
from app.api.whatsapp_webhook import router as whatsapp_router
from app.api.telegram_webhook import router as telegram_router
from app.api.razorpay_webhook import router as razorpay_router
from app.api.orders import router as orders_router
from app.api.printers import router as printers_router
from app.api.pricing import router as pricing_router
from app.api.analytics import router as analytics_router
from app.api.customers import router as customers_router
from app.api.settings import router as settings_router
from app.api.websocket import router as ws_router

all_routers = [
    auth_router,
    whatsapp_router,
    telegram_router,
    razorpay_router,
    orders_router,
    printers_router,
    pricing_router,
    analytics_router,
    customers_router,
    settings_router,
    ws_router,
]
