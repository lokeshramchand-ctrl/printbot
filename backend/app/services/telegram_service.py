import os
import httpx
import logging
from typing import List, Tuple, Dict, Any, Optional
from app.config import settings

logger = logging.getLogger("telegram_service")

class TelegramService:
    """Isolated Telegram Bot API Adapter."""

    def __init__(self):
        self.bot_token = settings.TELEGRAM_BOT_TOKEN
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

    async def send_text_message(self, chat_id: str, text: str) -> Optional[Dict[str, Any]]:
        """Send plain text message to Telegram user."""
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        return await self._post_request("sendMessage", payload)

    async def send_buttons(
        self, chat_id: str, body_text: str, buttons: List[Tuple[str, str]]
    ) -> Optional[Dict[str, Any]]:
        """
        Send message with Inline Keyboard Buttons.
        buttons format: [("btn_id_1", "Button Title 1"), ("btn_id_2", "Button Title 2")]
        """
        inline_keyboard = [
            [{"text": title, "callback_data": btn_id}]
            for btn_id, title in buttons
        ]
        payload = {
            "chat_id": chat_id,
            "text": body_text,
            "parse_mode": "Markdown",
            "reply_markup": {
                "inline_keyboard": inline_keyboard
            }
        }
        return await self._post_request("sendMessage", payload)

    async def send_payment_message(self, chat_id: str, order_summary_text: str, payment_url: str, amount_text: str) -> Optional[Dict[str, Any]]:
        """Send order summary with payment link button on Telegram."""
        inline_keyboard = [
            [{"text": f"💳 Pay {amount_text}", "url": payment_url}],
            [{"text": "❌ Cancel Order", "callback_data": "CANCEL_ORDER"}]
        ]
        payload = {
            "chat_id": chat_id,
            "text": f"{order_summary_text}\n\n⚡ Your order will be automatically printed immediately after payment completion.",
            "parse_mode": "Markdown",
            "reply_markup": {
                "inline_keyboard": inline_keyboard
            }
        }
        return await self._post_request("sendMessage", payload)

    async def download_incoming_file(self, file_id: str, save_path: str) -> bool:
        """Download document or photo uploaded by customer from Telegram API."""
        try:
            async with httpx.AsyncClient() as client:
                # Step 1: Get file path
                resp = await client.get(f"{self.base_url}/getFile?file_id={file_id}")
                if resp.status_code != 200:
                    logger.error(f"Telegram getFile error: {resp.text}")
                    return False
                
                file_path = resp.json().get("result", {}).get("file_path")
                if not file_path:
                    return False

                # Step 2: Download binary data
                file_url = f"https://api.telegram.org/file/bot{self.bot_token}/{file_path}"
                file_resp = await client.get(file_url)
                if file_resp.status_code == 200:
                    os.makedirs(os.path.dirname(save_path), exist_ok=True)
                    with open(save_path, "wb") as f:
                        f.write(file_resp.content)
                    return True
                else:
                    logger.error(f"Failed to download Telegram file binary from {file_url}: {file_resp.status_code}")
                    return False
        except Exception as e:
            logger.exception(f"Error downloading Telegram file {file_id}: {str(e)}")
            return False

    async def set_webhook(self, webhook_url: str) -> bool:
        """Register Telegram Webhook URL."""
        res = await self._post_request("setWebhook", {"url": webhook_url})
        return res is not None and res.get("ok") is True

    async def _post_request(self, endpoint: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Internal POST helper for Telegram API."""
        url = f"{self.base_url}/{endpoint}"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, timeout=10.0)
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"Telegram API Error [{response.status_code}]: {response.text}")
                    return None
        except Exception as e:
            logger.error(f"Telegram API Connection Exception: {str(e)}")
            return None

telegram_service = TelegramService()
