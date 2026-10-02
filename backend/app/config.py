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

    # Telegram Bot API (@capstoneprinterbot)
    TELEGRAM_BOT_TOKEN: str = ""
    
    # Razorpay Payment Gateway
    RAZORPAY_KEY_ID: str = "rzp_test_key_id"
    RAZORPAY_KEY_SECRET: str = "rzp_test_key_secret"
    RAZORPAY_WEBHOOK_SECRET: str = "rzp_webhook_secret_2026"
    
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

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()

# Ensure storage directories exist
os.makedirs(os.path.join(settings.STORAGE_DIR, "uploads"), exist_ok=True)
os.makedirs(os.path.join(settings.STORAGE_DIR, "processed"), exist_ok=True)
os.makedirs(os.path.join(settings.STORAGE_DIR, "previews"), exist_ok=True)
