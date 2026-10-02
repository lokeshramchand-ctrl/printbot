import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import all_routers
from app.api.auth import get_password_hash
from app.config import settings, validate_settings
from app.database import SessionLocal, initialize_mongodb
from app.models.admin import Admin
from app.services.cleanup_service import retention_loop
from app.services.pricing_service import pricing_service
from app.services.telegram_polling import telegram_poller

logger = logging.getLogger("printbot")

app = FastAPI(
    title=settings.APP_NAME,
    description="Multi-Channel Automated Printing System (WhatsApp + Telegram + Admin Dashboard)",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    # Credentials cannot be combined with a wildcard origin.
    allow_credentials="*" not in _origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Document preview images (thumbnails) only. Uploads and processed PDFs are
# served exclusively through the authenticated /api/orders/{id}/download route.
app.mount("/storage/previews", StaticFiles(directory=f"{settings.STORAGE_DIR}/previews"), name="previews")

for router in all_routers:
    app.include_router(router)

_background_tasks: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


@app.on_event("startup")
async def startup_event():
    """Validate config, seed defaults and start background services."""
    problems = validate_settings()
    if problems:
        for problem in problems:
            logger.error(f"CONFIG ERROR: {problem}")
        raise RuntimeError("Invalid configuration: " + " | ".join(problems))

    initialize_mongodb()
    db = SessionLocal()
    try:
        admin = db.query(Admin).filter(Admin.username == settings.ADMIN_DEFAULT_USERNAME).first()
        if not admin:
            db.add(Admin(
                username=settings.ADMIN_DEFAULT_USERNAME,
                email="admin@printbot.local",
                password_hash=get_password_hash(settings.ADMIN_DEFAULT_PASSWORD),
                role="SUPERADMIN"
            ))
            db.commit()
        pricing_service.seed_defaults_if_empty(db)
    finally:
        db.close()

    logger.info(f"PrintBot started: ENV={settings.ENV} PAYMENT_MODE={settings.PAYMENT_MODE}")
    if settings.PAYMENT_MODE == "demo":
        logger.warning("PAYMENT_MODE=demo: orders are 'paid' with a button, no money moves.")

    if settings.TELEGRAM_BOT_TOKEN:
        _spawn(telegram_poller.start_polling())
    _spawn(retention_loop())


@app.get("/")
def root_endpoint():
    return {
        "status": "online",
        "app": settings.APP_NAME,
        "version": "2.0.0",
        "payment_mode": settings.PAYMENT_MODE,
        "channels": ["WhatsApp", "Telegram"],
        "docs": "/docs"
    }


@app.get("/health")
def health():
    """Liveness probe incl. database reachability."""
    from app.database import get_client
    try:
        get_client().admin.command("ping")
        return {"status": "ok", "database": "up", "payment_mode": settings.PAYMENT_MODE}
    except Exception as e:
        return {"status": "degraded", "database": f"down: {e.__class__.__name__}"}
