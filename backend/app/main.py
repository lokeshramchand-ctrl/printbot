import os
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import initialize_mongodb, SessionLocal
from app.api import all_routers
from app.services.pricing_service import pricing_service
from app.services.telegram_polling import telegram_poller
from app.models.admin import Admin
from app.api.auth import get_password_hash

app = FastAPI(
    title=settings.APP_NAME,
    description="Multi-Channel Automated Printing System (WhatsApp + Telegram + Admin Dashboard)",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS Middleware setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Static storage directories for document preview images
app.mount("/storage", StaticFiles(directory=settings.STORAGE_DIR), name="storage")

# Include all API Routers
for router in all_routers:
    app.include_router(router)

@app.on_event("startup")
async def startup_event():
    """Seed initial defaults and initialize services."""
    initialize_mongodb()
    db = SessionLocal()
    try:
        # Seed default admin user if missing
        admin = db.query(Admin).filter(Admin.username == settings.ADMIN_DEFAULT_USERNAME).first()
        if not admin:
            admin = Admin(
                username=settings.ADMIN_DEFAULT_USERNAME,
                email="admin@printbot.local",
                password_hash=get_password_hash(settings.ADMIN_DEFAULT_PASSWORD),
                role="SUPERADMIN"
            )
            db.add(admin)
            db.commit()

        # Seed default pricing rules if empty
        pricing_service.seed_defaults_if_empty(db)
    finally:
        db.close()

    # Launch background Telegram polling when a bot token is configured.
    if settings.TELEGRAM_BOT_TOKEN:
        asyncio.create_task(telegram_poller.start_polling())

@app.get("/")
def root_endpoint():
    return {
        "status": "online",
        "app": settings.APP_NAME,
        "version": "2.0.0",
        "channels": ["WhatsApp", "Telegram"],
        "docs": "/docs"
    }
