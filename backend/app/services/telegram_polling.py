import asyncio
import logging

import httpx

from app.config import settings
from app.database import SessionLocal
from app.services.bot_state_machine import bot_state_machine

logger = logging.getLogger("telegram_polling")

OFFSET_KEY = "telegram_poll_offset"


class TelegramPoller:
    """Long-polling consumer (no public URL needed). Offset is persisted in MongoDB."""

    def __init__(self):
        self.offset = 0
        self.is_running = False
        self._tasks: set[asyncio.Task] = set()

    @property
    def base_url(self) -> str:
        return f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}"

    @staticmethod
    def _load_offset() -> int:
        db = SessionLocal()
        try:
            doc = db.database.bot_meta.find_one({"_id": OFFSET_KEY})
            return int(doc["value"]) if doc else 0
        finally:
            db.close()

    @staticmethod
    def _save_offset(offset: int) -> None:
        db = SessionLocal()
        try:
            db.database.bot_meta.update_one({"_id": OFFSET_KEY}, {"$set": {"value": offset}}, upsert=True)
        finally:
            db.close()

    async def _handle(self, update: dict) -> None:
        # Each update gets its own DB session; per-chat ordering is enforced by the state machine's chat lock.
        db = SessionLocal()
        try:
            await bot_state_machine.handle_telegram_update(db, update)
        except Exception:
            logger.exception("Unhandled error while processing Telegram update")
        finally:
            db.close()

    async def start_polling(self):
        """Poll Telegram getUpdates in a background task."""
        self.is_running = True
        self.offset = await asyncio.to_thread(self._load_offset)
        logger.info(f"Started Telegram long polling (offset {self.offset})")
        print("🤖 [TELEGRAM] Long polling active. Send a message on Telegram to test live.")

        async with httpx.AsyncClient(timeout=35.0) as client:
            # Polling and a registered webhook are mutually exclusive in Telegram.
            try:
                await client.post(f"{self.base_url}/deleteWebhook")
            except Exception as e:
                logger.warning(f"deleteWebhook failed: {e}")

            while self.is_running:
                try:
                    resp = await client.get(f"{self.base_url}/getUpdates",
                                            params={"offset": self.offset, "timeout": 20,
                                                    "allowed_updates": '["message","callback_query"]'})
                    if resp.status_code == 200 and resp.json().get("ok"):
                        for update in resp.json().get("result", []):
                            self.offset = update["update_id"] + 1
                            task = asyncio.create_task(self._handle(update))
                            self._tasks.add(task)
                            task.add_done_callback(self._tasks.discard)
                        if resp.json().get("result"):
                            await asyncio.to_thread(self._save_offset, self.offset)
                    elif resp.status_code == 409:
                        logger.warning("Telegram polling conflict: another getUpdates consumer is active.")
                        await asyncio.sleep(10)
                    else:
                        logger.error(f"Telegram polling error [{resp.status_code}]: {resp.text}")
                        await asyncio.sleep(5)
                except Exception as e:
                    logger.error(f"Telegram polling exception: {e}")
                    await asyncio.sleep(5)


telegram_poller = TelegramPoller()
