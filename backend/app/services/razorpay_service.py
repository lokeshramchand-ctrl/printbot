"""Razorpay Payment Links integration (production payment path).

Active only when ``PAYMENT_MODE=razorpay``. To go live: put real
``RAZORPAY_KEY_ID`` / ``RAZORPAY_KEY_SECRET`` in the environment, create a
webhook in the Razorpay dashboard pointing at ``<PUBLIC_BASE_URL>/webhooks/razorpay``
(events: ``payment_link.paid``, ``payment_link.expired``, ``payment_link.cancelled``,
``payment.failed``) and put its secret in ``RAZORPAY_WEBHOOK_SECRET``.
"""
import asyncio
import hashlib
import hmac
import logging
import re
import time
from typing import Any, Dict, Optional

import razorpay

from app.config import razorpay_configured, settings

logger = logging.getLogger("razorpay_service")

PAYMENT_LINK_EXPIRY_MINUTES = 60  # Razorpay requires expire_by to be >= 15 minutes ahead


def _valid_phone(value: Optional[str]) -> Optional[str]:
    """Return a Razorpay-acceptable contact number, or None (e.g. Telegram chat ids are not phones)."""
    if not value or value.startswith("tg_"):
        return None
    digits = re.sub(r"[^\d+]", "", value)
    return digits if re.fullmatch(r"\+?\d{10,15}", digits) else None


class RazorpayService:
    """Thin, testable wrapper around the official Razorpay SDK."""

    def __init__(self):
        self._client: Any = None

    @property
    def client(self):
        if self._client is None:
            # Read credentials lazily so tests/ops can set them after import.
            self._client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
            self._client.set_app_details({"title": "PrintBot", "version": "2.0"})
        return self._client

    @property
    def is_configured(self) -> bool:
        return razorpay_configured()

    async def create_payment_link(
        self, order_id: str, amount_inr: float, customer_phone: Optional[str], description: str
    ) -> Dict[str, Any]:
        """Create a single-use payment link. Never returns a fake URL."""
        if not self.is_configured:
            return {"success": False, "error": "Razorpay is not configured with valid API credentials."}

        payload: Dict[str, Any] = {
            "amount": int(round(amount_inr * 100)),
            "currency": "INR",
            "accept_partial": False,
            "reference_id": order_id,
            "description": description[:2048],
            "expire_by": int(time.time()) + PAYMENT_LINK_EXPIRY_MINUTES * 60,
            # We deliver the link ourselves in the chat; avoid double SMS/WhatsApp from Razorpay.
            "notify": {"sms": False, "email": False},
            "reminder_enable": False,
            "notes": {"order_id": order_id, "app": "PrintBot"},
        }
        phone = _valid_phone(customer_phone)
        if phone:
            payload["customer"] = {"contact": phone}

        try:
            res = await asyncio.to_thread(self.client.payment_link.create, payload)
        except Exception as e:  # SDK raises BadRequestError / network errors
            logger.error(f"Razorpay payment link error for {order_id}: {e}")
            return {"success": False, "error": f"Razorpay error: {e}"}

        url = res.get("short_url") or res.get("url")
        if not url:
            return {"success": False, "error": "Razorpay returned no payment URL."}
        return {"success": True, "payment_link_id": res.get("id"), "payment_url": url, "expire_by": res.get("expire_by")}

    async def cancel_payment_link(self, payment_link_id: str) -> bool:
        """Cancel an unpaid link so a cancelled order can no longer be paid."""
        if not self.is_configured or not payment_link_id:
            return False
        try:
            await asyncio.to_thread(self.client.payment_link.cancel, payment_link_id)
            return True
        except Exception as e:
            logger.warning(f"Could not cancel Razorpay payment link {payment_link_id}: {e}")
            return False

    async def refund_payment(self, payment_id: str, amount_inr: Optional[float] = None) -> Dict[str, Any]:
        """Refund a captured payment (full if amount omitted)."""
        if not self.is_configured:
            return {"success": False, "error": "Razorpay is not configured."}
        data: Dict[str, Any] = {}
        if amount_inr is not None:
            data["amount"] = int(round(amount_inr * 100))
        try:
            res = await asyncio.to_thread(self.client.payment.refund, payment_id, data)
            return {"success": True, "refund_id": res.get("id"), "raw_response": res}
        except Exception as e:
            logger.error(f"Razorpay refund failed for {payment_id}: {e}")
            return {"success": False, "error": str(e)}

    def verify_webhook_signature(self, body_bytes: bytes, signature: Optional[str]) -> bool:
        """Verify the ``X-Razorpay-Signature`` HMAC-SHA256 of the raw request body."""
        secret = settings.RAZORPAY_WEBHOOK_SECRET
        if not signature or not secret:
            return False
        expected = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)


razorpay_service = RazorpayService()
