import httpx
import logging
import os
from typing import List, Tuple, Dict, Any, Optional
from app.config import settings

logger = logging.getLogger("whatsapp_service")

class WhatsAppService:
    """
    Isolated WhatsApp Business Cloud API Adapter.
    Can be replaced or wrapped for alternative WhatsApp providers if needed.
    """
    def __init__(self):
        self.access_token = settings.WHATSAPP_ACCESS_TOKEN
        self.phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
        self.api_version = settings.WHATSAPP_API_VERSION
        self.base_url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}"
        
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    async def send_text_message(self, to_phone: str, text: str) -> Optional[Dict[str, Any]]:
        """Send a plain text message via WhatsApp."""
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }
        return await self._post_request("messages", payload)

    async def send_buttons(
        self, to_phone: str, body_text: str, buttons: List[Tuple[str, str]], header_text: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Send interactive button message.
        buttons format: [("btn_id_1", "Button Title 1"), ("btn_id_2", "Button Title 2")]
        Max 3 buttons supported per WhatsApp interactive payload.
        """
        if len(buttons) > 3:
            # Fallback to text message if buttons exceed limit
            button_list_text = "\n".join([f"{i+1}️⃣ {title}" for i, (_, title) in enumerate(buttons)])
            full_text = f"{body_text}\n\n{button_list_text}\n\nReply with your option number or text."
            return await self.send_text_message(to_phone, full_text)

        action_buttons = [
            {
                "type": "reply",
                "reply": {"id": btn_id, "title": title[:20]} # WhatsApp 20 char limit on button title
            }
            for btn_id, title in buttons
        ]

        interactive_obj = {
            "type": "button",
            "body": {"text": body_text},
            "action": {"buttons": action_buttons},
        }

        if header_text:
            interactive_obj["header"] = {"type": "text", "text": header_text}

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone,
            "type": "interactive",
            "interactive": interactive_obj,
        }
        return await self._post_request("messages", payload)

    async def send_payment_message(
        self, to_phone: str, order_summary_text: str, amount_text: str, order_id: str, payment_url: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Order summary with a pay action (real link, or a demo confirm button)."""
        if payment_url:
            message_text = (
                f"{order_summary_text}\n\n"
                f"💳 *Pay {amount_text}:*\n{payment_url}\n\n"
                "⚡ Your order will be printed automatically right after payment."
            )
            buttons = [("CANCEL_ORDER", "❌ Cancel Order")]
        else:
            message_text = f"{order_summary_text}\n\n🧪 Demo mode: tap Pay to simulate a successful payment."
            buttons = [(f"DEMO_PAY_{order_id}", f"💳 Pay {amount_text}"), ("CANCEL_ORDER", "❌ Cancel Order")]
        return await self.send_buttons(to_phone, message_text, buttons)

    async def download_incoming_media(self, media_id: str, save_path: str) -> bool:
        """Download media uploaded by customer via WhatsApp API."""
        try:
            async with httpx.AsyncClient() as client:
                # Step 1: Get media URL
                media_info_url = f"https://graph.facebook.com/{self.api_version}/{media_id}"
                resp = await client.get(media_info_url, headers={"Authorization": f"Bearer {self.access_token}"})
                if resp.status_code != 200:
                    logger.error(f"Failed to fetch media metadata for {media_id}: {resp.text}")
                    return False
                
                download_url = resp.json().get("url")
                if not download_url:
                    return False

                # Step 2: Download binary data
                file_resp = await client.get(download_url, headers={"Authorization": f"Bearer {self.access_token}"})
                if file_resp.status_code == 200:
                    os.makedirs(os.path.dirname(save_path), exist_ok=True)
                    with open(save_path, "wb") as f:
                        f.write(file_resp.content)
                    return True
                else:
                    logger.error(f"Failed to download media binary from {download_url}: {file_resp.status_code}")
                    return False
        except Exception as e:
            logger.exception(f"Error downloading media {media_id}: {str(e)}")
            return False

    async def mark_message_as_read(self, message_id: str) -> bool:
        """Mark incoming message as read."""
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id
        }
        res = await self._post_request("messages", payload)
        return res is not None

    async def _post_request(self, endpoint: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Internal helper for API POST requests."""
        url = f"{self.base_url}/{endpoint}"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, headers=self.headers, json=payload, timeout=10.0)
                if response.status_code in (200, 201):
                    return response.json()
                else:
                    logger.error(f"WhatsApp API Error [{response.status_code}]: {response.text}")
                    return None
        except Exception as e:
            logger.error(f"WhatsApp API Connection Exception: {str(e)}")
            return None

whatsapp_service = WhatsAppService()
