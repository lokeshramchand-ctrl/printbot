import hmac
import hashlib
import logging
import razorpay
from typing import Dict, Any, Optional
from app.config import settings

logger = logging.getLogger("razorpay_service")

class RazorpayService:
    """Razorpay payment gateway integration service."""

    def __init__(self):
        self.key_id = settings.RAZORPAY_KEY_ID
        self.key_secret = settings.RAZORPAY_KEY_SECRET
        self.webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET
        
        # Initialize official Razorpay SDK client if keys configured
        try:
            self.client = razorpay.Client(auth=(self.key_id, self.key_secret))
        except Exception as e:
            logger.warning(f"Razorpay Client initialization warning: {str(e)}")
            self.client = None

    def create_payment_link(self, order_id: str, amount_inr: float, customer_phone: str, description: str) -> Dict[str, Any]:
        """
        Creates a Razorpay Payment Link for the order.
        Returns payment_link_id and payment_url.
        """
        amount_paise = int(round(amount_inr * 100))

        # Check if production/valid keys exist
        is_test_placeholder = (self.key_id == "rzp_test_key_id" or not self.key_id)

        if not is_test_placeholder and self.client:
            try:
                payload = {
                    "amount": amount_paise,
                    "currency": "INR",
                    "accept_partial": False,
                    "reference_id": order_id,
                    "description": description,
                    "customer": {
                        "contact": customer_phone,
                    },
                    "notify": {
                        "sms": True,
                        "whatsapp": True
                    },
                    "reminder_enable": True,
                    "notes": {
                        "order_id": order_id,
                        "app": "PrintBot"
                    }
                }
                res = self.client.payment_link.create(payload)
                return {
                    "success": True,
                    "payment_link_id": res.get("id"),
                    "payment_url": res.get("short_url") or res.get("url"),
                    "raw_response": res
                }
            except Exception as e:
                logger.error(f"Razorpay Payment Link API error for {order_id}: {str(e)}")

        # Do not send a fake hosted URL: it looks valid to the customer but
        # returns 404 and leaves the order stuck in PAYMENT_PENDING.
        return {
            "success": False,
            "error": "Razorpay is not configured with valid API credentials."
        }

    def verify_webhook_signature(self, body_bytes: bytes, signature: str) -> bool:
        """Verifies Razorpay webhook HMAC-SHA256 signature."""
        if not signature or not self.webhook_secret:
            return False
            
        try:
            expected_signature = hmac.new(
                key=self.webhook_secret.encode("utf-8"),
                msg=body_bytes,
                digestmod=hashlib.sha256
            ).hexdigest()
            return hmac.compare_digest(expected_signature, signature)
        except Exception as e:
            logger.error(f"Error verifying Razorpay webhook signature: {str(e)}")
            return False

razorpay_service = RazorpayService()
