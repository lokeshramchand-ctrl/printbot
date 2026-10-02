"""Channel-agnostic outbound messaging (Telegram / WhatsApp).

Everything that talks to a customer -- the bot state machine, the payment
pipeline, admin actions -- goes through here so a Telegram customer is never
accidentally messaged on WhatsApp (the old webhook/admin code did that).
"""
from typing import List, Optional, Tuple

from app.services.telegram_service import telegram_service
from app.services.whatsapp_service import whatsapp_service


def _is_telegram(customer) -> bool:
    return customer.channel == "TELEGRAM" and bool(customer.telegram_chat_id)


async def send_message(customer, text: str):
    if _is_telegram(customer):
        return await telegram_service.send_text_message(customer.telegram_chat_id, text)
    return await whatsapp_service.send_text_message(customer.whatsapp_number, text)


async def send_buttons(customer, text: str, buttons: List[Tuple[str, str]]):
    if _is_telegram(customer):
        return await telegram_service.send_buttons(customer.telegram_chat_id, text, buttons)
    return await whatsapp_service.send_buttons(customer.whatsapp_number, text, buttons)


async def send_payment_prompt(
    customer, summary_text: str, amount_text: str, order_id: str, payment_url: Optional[str] = None
):
    """Order summary + pay action.

    ``payment_url`` set  -> real checkout link (Razorpay).
    ``payment_url`` None -> demo mode: a button that confirms payment in-bot.
    """
    if _is_telegram(customer):
        return await telegram_service.send_payment_message(
            customer.telegram_chat_id, summary_text, amount_text, order_id, payment_url
        )
    return await whatsapp_service.send_payment_message(
        customer.whatsapp_number, summary_text, amount_text, order_id, payment_url
    )
