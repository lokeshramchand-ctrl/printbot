import asyncio
import httpx
import logging
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.services.bot_state_machine import bot_state_machine
from app.config import settings

logger = logging.getLogger("telegram_polling")

class TelegramPoller:
    """Long-polling service for local testing without ngrok/webhooks."""

    def __init__(self):
        self.bot_token = settings.TELEGRAM_BOT_TOKEN
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.offset = 0
        self.is_running = False

    async def start_polling(self):
        """Poll Telegram getUpdates in a background task."""
        self.is_running = True
        logger.info("Started Telegram long polling")
        print("🤖 [TELEGRAM] Long polling active. Send a message on Telegram to test live.")

        async with httpx.AsyncClient(timeout=30.0) as client:
            while self.is_running:
                try:
                    url = f"{self.base_url}/getUpdates?offset={self.offset}&timeout=20"
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("ok"):
                            updates = data.get("result", [])
                            for update in updates:
                                self.offset = update["update_id"] + 1
                                db: Session = SessionLocal()
                                try:
                                    await bot_state_machine.handle_telegram_update(db, update)
                                finally:
                                    db.close()
                    elif resp.status_code == 409:
                        logger.warning("Telegram polling conflict: another getUpdates consumer is active.")
                        await asyncio.sleep(10)
                    else:
                        logger.error(f"Telegram polling error [{resp.status_code}]: {resp.text}")
                        await asyncio.sleep(5)
                except Exception as e:
                    logger.error(f"Telegram polling exception: {str(e)}")
                    await asyncio.sleep(5)

    def stop_polling(self):
        self.is_running = False

telegram_poller = TelegramPoller()
