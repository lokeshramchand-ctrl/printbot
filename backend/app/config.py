import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    APP_NAME: str = "PrintBot Automated Printing System"
    ENV: str = "development"
    DEBUG: bool = True
    
    # Database
    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DATABASE: str = "printbot"
    
    # JWT Authentication
    SECRET_KEY: str = "printbot_super_secret_jwt_key_change_in_production_2026"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 # 24 hours
    ADMIN_DEFAULT_USERNAME: str = "admin"
    ADMIN_DEFAULT_PASSWORD: str = "admin123"
    
    # WhatsApp Business Cloud API
    WHATSAPP_ACCESS_TOKEN: str = "EAAG..."
    WHATSAPP_PHONE_NUMBER_ID: str = "100000000000000"
    WHATSAPP_VERIFY_TOKEN: str = "printbot_verify_token_2026"
    WHATSAPP_API_VERSION: str = "v19.0"
    # Meta app secret: when set, inbound webhooks must carry a valid X-Hub-Signature-256.
    WHATSAPP_APP_SECRET: str = ""

    # Telegram Bot API (@capstoneprinterbot)
    TELEGRAM_BOT_TOKEN: str = ""
    # Optional shared secret Telegram echoes back in the
    # X-Telegram-Bot-Api-Secret-Token header when a webhook is registered.
    TELEGRAM_WEBHOOK_SECRET: str = ""

    # Public HTTPS base URL of this backend (ngrok/cloudflared/prod domain).
    PUBLIC_BASE_URL: str = ""

    # How customers pay:
    #   demo     -> order summary shows a "Pay (Demo)" button; tapping it runs
    #               the exact same post-payment pipeline as a real payment
    #               (mark PAID -> queue -> print -> notify). No money moves.
    #   razorpay -> real Razorpay payment link + signed webhook confirmation.
    PAYMENT_MODE: str = "demo"

    # Razorpay Payment Gateway (used only when PAYMENT_MODE=razorpay)
    RAZORPAY_KEY_ID: str = "rzp_test_key_id"
    RAZORPAY_KEY_SECRET: str = "rzp_test_key_secret"
    RAZORPAY_WEBHOOK_SECRET: str = "rzp_webhook_secret_2026"
    # Browser origins allowed to call the API (comma separated). "*" only in development.
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost"
    MAX_COPIES: int = 100
    
    # Storage & File Retention
    STORAGE_DIR: str = str(BASE_DIR / "storage")
    FILE_RETENTION_DAYS: int = 7
    MAX_FILE_SIZE_MB: int = 50
    
    # CUPS / Printer Configuration
    CUPS_HOST: str = "localhost"
    CUPS_PORT: int = 631
    USE_VIRTUAL_PRINTER: bool = True  # Fallback to simulated virtual printer when CUPS is unavailable
    
    # Business Details
    BUSINESS_NAME: str = "PrintBot Express"
    BUSINESS_PHONE: str = "+919876543210"
    PICKUP_ADDRESS: str = "Main Store, Central Library Complex, Campus Gate 1"

    # Print serial numbering — human-readable prefix for the per-order
    # PB-YYYYMMDD-NNNNNN reference stamped on every printed page.
    SERIAL_PREFIX: str = "PB"

    # Separator/cover sheet with a large pickup code printed on top of each order's stack.
    # Only used for orders with at least COVER_SHEET_MIN_PAGES pages (dashboard-toggleable).
    COVER_SHEET_ENABLED: bool = True
    COVER_SHEET_MIN_PAGES: int = 2
    # Copies are expanded into the PDF (so each carries its own "Copy n/m" stamp) up to this many pages.
    MAX_EXPANDED_PAGES: int = 1500

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()

RAZORPAY_PLACEHOLDERS = {"", "rzp_test_key_id", "rzp_test_key_secret", "your_razorpay_key_id", "your_razorpay_key_secret"}
INSECURE_SECRET_KEYS = {
    "printbot_super_secret_jwt_key_change_in_production_2026",
    "change_this_to_a_secure_random_secret_key_in_production",
    "",
}


def razorpay_configured() -> bool:
    """True only when real (non-placeholder) key id, key secret and webhook secret are set."""
    return (
        settings.RAZORPAY_KEY_ID not in RAZORPAY_PLACEHOLDERS
        and settings.RAZORPAY_KEY_SECRET not in RAZORPAY_PLACEHOLDERS
        and settings.RAZORPAY_WEBHOOK_SECRET not in ("", "rzp_webhook_secret_2026", "your_razorpay_webhook_secret")
    )


def validate_settings() -> list[str]:
    """Return fatal configuration problems for the current ENV/PAYMENT_MODE.

    Called at startup. Production refuses to boot with demo payments,
    placeholder Razorpay credentials, default admin/JWT secrets or open CORS.
    """
    problems: list[str] = []
    if settings.PAYMENT_MODE not in ("demo", "razorpay"):
        problems.append("PAYMENT_MODE must be 'demo' or 'razorpay'.")
    if settings.PAYMENT_MODE == "razorpay" and not razorpay_configured():
        problems.append("PAYMENT_MODE=razorpay requires real RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET and RAZORPAY_WEBHOOK_SECRET.")
    if settings.ENV.lower() == "production":
        if settings.PAYMENT_MODE == "demo":
            problems.append("ENV=production must not use PAYMENT_MODE=demo (customers would print for free).")
        if settings.SECRET_KEY in INSECURE_SECRET_KEYS or len(settings.SECRET_KEY) < 32:
            problems.append("SECRET_KEY must be a random value of at least 32 characters in production.")
        if settings.ADMIN_DEFAULT_PASSWORD == "admin123":
            problems.append("ADMIN_DEFAULT_PASSWORD must be changed in production.")
        if not settings.WHATSAPP_APP_SECRET and settings.WHATSAPP_ACCESS_TOKEN not in ("", "EAAG..."):
            problems.append("WHATSAPP_APP_SECRET must be set when WhatsApp is configured (webhook signature check).")
        if settings.CORS_ORIGINS.strip() == "*":
            problems.append("CORS_ORIGINS must list explicit origins in production.")
    return problems

# Ensure storage directories exist
os.makedirs(os.path.join(settings.STORAGE_DIR, "uploads"), exist_ok=True)
os.makedirs(os.path.join(settings.STORAGE_DIR, "processed"), exist_ok=True)
os.makedirs(os.path.join(settings.STORAGE_DIR, "previews"), exist_ok=True)
