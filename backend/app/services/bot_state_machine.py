import os
import logging
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from typing import Dict, Any, Optional, List, Tuple
from app.models.customer import Customer
from app.models.order import Order
from app.models.message import WhatsAppMessage
from app.models.history import OrderStatusHistory
from app.services.whatsapp_service import whatsapp_service
from app.services.telegram_service import telegram_service
from app.services.document_service import document_service
from app.services.pricing_service import pricing_service
from app.services.razorpay_service import razorpay_service
from app.services.print_service import print_service
from app.utils.helpers import generate_order_id, sanitize_filename
from app.config import settings

logger = logging.getLogger("bot_state_machine")

class BotStateMachine:
    """Multi-Channel Conversational State Machine managing WhatsApp & Telegram customer experience."""

    # --- Outbound Channel Dispatchers ---

    async def _send_message(self, customer: Customer, text: str):
        """Dispatches message to WhatsApp or Telegram based on customer channel."""
        if customer.channel == "TELEGRAM" and customer.telegram_chat_id:
            await telegram_service.send_text_message(customer.telegram_chat_id, text)
        else:
            await whatsapp_service.send_text_message(customer.whatsapp_number, text)

    async def _send_buttons(self, customer: Customer, text: str, buttons: List[Tuple[str, str]]):
        """Dispatches interactive buttons to active channel."""
        if customer.channel == "TELEGRAM" and customer.telegram_chat_id:
            await telegram_service.send_buttons(customer.telegram_chat_id, text, buttons)
        else:
            await whatsapp_service.send_buttons(customer.whatsapp_number, text, buttons)

    async def _send_payment_msg(self, customer: Customer, summary_text: str, payment_url: str, amount_text: str):
        """Dispatches payment link summary to active channel."""
        if customer.channel == "TELEGRAM" and customer.telegram_chat_id:
            await telegram_service.send_payment_message(customer.telegram_chat_id, summary_text, payment_url, amount_text)
        else:
            await whatsapp_service.send_payment_message(customer.whatsapp_number, summary_text, payment_url, amount_text)

    # --- Inbound WhatsApp Processing ---

    async def handle_inbound_message(self, db: Session, payload: Dict[str, Any]):
        """Entry point for incoming WhatsApp webhooks."""
        try:
            value = payload.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {})
            contacts = value.get("contacts", [{}])
            messages = value.get("messages", [])

            if not messages:
                return

            msg = messages[0]
            from_phone = msg.get("from")
            whatsapp_msg_id = msg.get("id")
            msg_type = msg.get("type")
            contact_name = contacts[0].get("profile", {}).get("name") if contacts else "Customer"

            if not from_phone:
                return

            await whatsapp_service.mark_message_as_read(whatsapp_msg_id)

            customer = db.query(Customer).filter(Customer.whatsapp_number == from_phone).first()
            if not customer:
                customer = Customer(
                    channel="WHATSAPP",
                    whatsapp_number=from_phone,
                    display_name=contact_name,
                    bot_state="IDLE",
                    state_data={}
                )
                db.add(customer)
                db.commit()
                db.refresh(customer)

            text_body = ""
            media_id = None
            if msg_type == "text":
                text_body = msg.get("text", {}).get("body", "").strip()
            elif msg_type == "interactive":
                interactive = msg.get("interactive", {})
                if interactive.get("type") == "button_reply":
                    text_body = interactive.get("button_reply", {}).get("title", "").strip()
                elif interactive.get("type") == "list_reply":
                    text_body = interactive.get("list_reply", {}).get("title", "").strip()
            elif msg_type in ("document", "image"):
                media_obj = msg.get(msg_type, {})
                media_id = media_obj.get("id")
                text_body = media_obj.get("filename") or f"Uploaded {msg_type}"

            await self._process_state_transition(db, customer, text_body, media_id, msg_type, msg)

        except Exception as e:
            logger.exception(f"Error handling WhatsApp inbound message: {str(e)}")

    # --- Inbound Telegram Processing ---

    async def handle_telegram_update(self, db: Session, update: Dict[str, Any]):
        """Entry point for incoming Telegram updates."""
        try:
            message = update.get("message")
            callback_query = update.get("callback_query")

            if callback_query:
                chat_id = str(callback_query.get("message", {}).get("chat", {}).get("id"))
                from_name = callback_query.get("from", {}).get("first_name", "Telegram User")
                text_body = callback_query.get("data", "").strip()
                msg_type = "button_callback"
                media_id = None
            elif message:
                chat_id = str(message.get("chat", {}).get("id"))
                from_name = message.get("from", {}).get("first_name", "Telegram User")
                text_body = message.get("text", "").strip()
                msg_type = "text"
                media_id = None

                if "document" in message:
                    doc = message["document"]
                    media_id = doc.get("file_id")
                    text_body = doc.get("file_name") or "document.pdf"
                    msg_type = "document"
                elif "photo" in message:
                    photos = message["photo"]
                    media_id = photos[-1].get("file_id") # Highest resolution photo
                    text_body = "photo.jpg"
                    msg_type = "image"
            else:
                return

            if not chat_id:
                return

            customer = db.query(Customer).filter(Customer.telegram_chat_id == chat_id).first()
            if not customer:
                customer = Customer(
                    channel="TELEGRAM",
                    telegram_chat_id=chat_id,
                    whatsapp_number=f"tg_{chat_id}",
                    display_name=from_name,
                    bot_state="IDLE",
                    state_data={}
                )
                db.add(customer)
                db.commit()
                db.refresh(customer)

            await self._process_state_transition(db, customer, text_body, media_id, msg_type, update)

        except Exception as e:
            logger.exception(f"Error handling Telegram update: {str(e)}")

    # --- Common Conversational Transition Router ---

    async def _process_state_transition(
        self, db: Session, customer: Customer, text_body: str, media_id: Optional[str], msg_type: str, raw_obj: Dict[str, Any]
    ):
        cmd = text_body.upper() if text_body else ""

        # Global commands
        if cmd in ("CANCEL", "STOP", "CANCEL_ORDER"):
            await self._handle_global_cancel(db, customer)
            return
        elif cmd in ("RESTART", "RESET", "/START"):
            await self._handle_global_restart(db, customer)
            return
        elif cmd in ("STATUS", "/STATUS"):
            await self._handle_global_status(db, customer)
            return
        elif cmd in ("HELP", "/HELP"):
            await self._handle_global_help(db, customer)
            return

        state = customer.bot_state

        if state == "IDLE":
            if msg_type in ("document", "image"):
                await self._process_file_upload(db, customer, media_id, text_body, msg_type)
            else:
                await self._send_greeting(db, customer)

        elif state == "WAITING_FOR_FILE":
            if msg_type in ("document", "image"):
                await self._process_file_upload(db, customer, media_id, text_body, msg_type)
            else:
                await self._send_message(
                    customer,
                    "📄 Please send your PDF, Word document (DOC/DOCX), or image (JPG/PNG) to begin printing."
                )

        elif state == "ASK_COPIES":
            await self._handle_copies_input(db, customer, text_body)

        elif state == "ASK_COLOR":
            await self._handle_color_input(db, customer, text_body)

        elif state == "ASK_PAPER_SIZE":
            await self._handle_paper_size_input(db, customer, text_body)

        elif state == "ASK_PAGES":
            await self._handle_pages_input(db, customer, text_body)

        elif state == "ASK_SIDES":
            await self._handle_sides_input(db, customer, text_body)

        elif state == "WAITING_FOR_PAYMENT":
            await self._send_message(
                customer,
                "💳 We are waiting for payment for your order. Click the payment link above to complete your order, or reply 'CANCEL' to start over."
            )

        else:
            customer.bot_state = "IDLE"
            db.commit()
            await self._send_greeting(db, customer)

    # --- Conversational Actions ---

    async def _send_greeting(self, db: Session, customer: Customer):
        greeting = (
            f"👋 Welcome to *{settings.BUSINESS_NAME}*!\n\n"
            "I can print your documents directly.\n\n"
            "📄 Send me your PDF, Word document (DOC/DOCX), JPG or PNG to get started."
        )
        customer.bot_state = "WAITING_FOR_FILE"
        customer.state_data = {}
        flag_modified(customer, "state_data")
        db.commit()
        await self._send_message(customer, greeting)

    async def _process_file_upload(self, db: Session, customer: Customer, media_id: Optional[str], filename: str, msg_type: str):
        if not document_service.is_supported(filename):
            reject_msg = (
                "❌ *Unsupported file type.*\n\n"
                "Please send:\n"
                "📄 PDF (.pdf)\n"
                "📝 Word (.doc, .docx)\n"
                "🖼️ Image (.jpg, .jpeg, .png)"
            )
            await self._send_message(customer, reject_msg)
            return

        temp_order_id = generate_order_id()
        raw_download_path = os.path.join(settings.STORAGE_DIR, "uploads", f"{temp_order_id}_{sanitize_filename(filename)}")

        await self._send_message(customer, "⏳ Downloading and processing your file...")

        if customer.channel == "TELEGRAM":
            download_success = await telegram_service.download_incoming_file(media_id, raw_download_path)
        else:
            download_success = await whatsapp_service.download_incoming_media(media_id, raw_download_path)

        if not download_success:
            await self._send_message(customer, "❌ Could not download file. Please try sending the document again.")
            return

        proc_result = document_service.process_file(raw_download_path, temp_order_id, filename)
        if not proc_result.get("success"):
            await self._send_message(customer, f"❌ {proc_result.get('error', 'Could not process document.')}\n\nPlease try uploading again.")
            return

        page_count = proc_result["page_count"]
        pdf_path = proc_result["pdf_path"]

        state_data = {
            "temp_order_id": temp_order_id,
            "filename": filename,
            "raw_path": raw_download_path,
            "pdf_path": pdf_path,
            "page_count": page_count,
            "file_type": proc_result["file_type"],
            "file_size": proc_result["file_size"],
        }
        customer.state_data = state_data
        customer.bot_state = "ASK_COPIES"
        flag_modified(customer, "state_data")
        db.commit()

        body_text = (
            f"✅ *File received!*\n\n"
            f"📄 File: *{filename}*\n"
            f"📑 Pages: *{page_count}*\n\n"
            "Choose the number of copies:"
        )
        buttons = [
            ("COPIES_1", "1️⃣ 1 copy"),
            ("COPIES_2", "2️⃣ 2 copies"),
            ("COPIES_3", "3️⃣ 3 copies"),
        ]
        await self._send_buttons(customer, body_text, buttons)

    async def _handle_copies_input(self, db: Session, customer: Customer, input_text: str):
        copies = 1
        cleaned = input_text.lower().replace("copy", "").replace("copies", "").strip()
        if "1" in cleaned or "copies_1" in cleaned:
            copies = 1
        elif "2" in cleaned or "copies_2" in cleaned:
            copies = 2
        elif "3" in cleaned or "copies_3" in cleaned:
            copies = 3
        elif "5" in cleaned:
            copies = 5
        elif cleaned.isdigit():
            copies = max(1, int(cleaned))

        state_data = dict(customer.state_data or {})
        state_data["copies"] = copies
        customer.state_data = state_data
        customer.bot_state = "ASK_COLOR"
        flag_modified(customer, "state_data")
        db.commit()

        body_text = "Choose printing type:\n\n🖤 Black & White\n🌈 Color"
        buttons = [
            ("COLOR_BW", "🖤 B&W"),
            ("COLOR_COLOR", "🌈 Color")
        ]
        await self._send_buttons(customer, body_text, buttons)

    async def _handle_color_input(self, db: Session, customer: Customer, input_text: str):
        cleaned = input_text.upper()
        if "COLOR" in cleaned or "2" in cleaned or "🌈" in cleaned or "COLOR_COLOR" in cleaned:
            color_mode = "Color"
        else:
            color_mode = "BW"

        state_data = dict(customer.state_data or {})
        state_data["color_mode"] = color_mode
        customer.state_data = state_data
        customer.bot_state = "ASK_PAPER_SIZE"
        flag_modified(customer, "state_data")
        db.commit()

        body_text = "Choose paper size:\n\n📄 A4\n📄 A3\n📄 Letter"
        buttons = [
            ("PAPER_A4", "📄 A4"),
            ("PAPER_A3", "📄 A3"),
            ("PAPER_LETTER", "📄 Letter")
        ]
        await self._send_buttons(customer, body_text, buttons)

    async def _handle_paper_size_input(self, db: Session, customer: Customer, input_text: str):
        cleaned = input_text.upper()
        if "A3" in cleaned or "PAPER_A3" in cleaned:
            paper_size = "A3"
        elif "LETTER" in cleaned or "PAPER_LETTER" in cleaned:
            paper_size = "Letter"
        else:
            paper_size = "A4"

        state_data = dict(customer.state_data or {})
        state_data["paper_size"] = paper_size
        customer.state_data = state_data
        customer.bot_state = "ASK_PAGES"
        flag_modified(customer, "state_data")
        db.commit()

        body_text = "Choose pages:\n\n1️⃣ All pages\n2️⃣ Specific pages"
        buttons = [
            ("PAGES_ALL", "1️⃣ All pages"),
            ("PAGES_SPECIFIC", "2️⃣ Specific pages")
        ]
        await self._send_buttons(customer, body_text, buttons)

    async def _handle_pages_input(self, db: Session, customer: Customer, input_text: str):
        state_data = dict(customer.state_data or {})
        state_data["pages_to_print"] = "all"
        customer.state_data = state_data
        customer.bot_state = "ASK_SIDES"
        flag_modified(customer, "state_data")
        db.commit()

        body_text = "Do you want:\n\n1️⃣ Single-sided\n2️⃣ Double-sided"
        buttons = [
            ("SIDES_SINGLE", "1️⃣ Single-sided"),
            ("SIDES_DOUBLE", "2️⃣ Double-sided")
        ]
        await self._send_buttons(customer, body_text, buttons)

    async def _handle_sides_input(self, db: Session, customer: Customer, input_text: str):
        cleaned = input_text.lower()
        if "double" in cleaned or "2" in cleaned or "sides_double" in cleaned:
            sides = "double"
        else:
            sides = "single"

        state_data = dict(customer.state_data or {})
        state_data["sides"] = sides

        filename = state_data.get("filename", "document.pdf")
        page_count = state_data.get("page_count", 1)
        copies = state_data.get("copies", 1)
        paper_size = state_data.get("paper_size", "A4")
        color_mode = state_data.get("color_mode", "BW")
        pdf_path = state_data.get("pdf_path")
        raw_path = state_data.get("raw_path")

        price_info = pricing_service.calculate_price(
            db, paper_size, color_mode, sides, page_count, copies
        )
        total_amount = price_info["total_amount"]

        order_id = generate_order_id()
        order = Order(
            id=order_id,
            customer_id=customer.id,
            channel=customer.channel,
            original_file_name=filename,
            stored_file_path=raw_path,
            printable_pdf_path=pdf_path,
            file_type=state_data.get("file_type", "PDF"),
            file_size_bytes=state_data.get("file_size", 0),
            total_pages=page_count,
            copies=copies,
            paper_size=paper_size,
            color_mode=color_mode,
            sides=sides,
            pages_to_print="all",
            rate_per_page=price_info["rate_per_page"],
            subtotal_amount=price_info["subtotal"],
            additional_charges=price_info["additional_charge"],
            total_amount=total_amount,
            payment_status="PENDING",
            current_state="PAYMENT_PENDING"
        )
        db.add(order)

        history = OrderStatusHistory(
            order_id=order_id,
            from_status="CONFIGURING",
            to_status="PAYMENT_PENDING",
            trigger_source="BOT",
            notes=f"Order calculated: ₹{total_amount}"
        )
        db.add(history)
        db.commit()
        db.refresh(order)

        contact_num = customer.whatsapp_number if customer.channel == "WHATSAPP" else (customer.telegram_chat_id or "9999999999")
        pay_res = razorpay_service.create_payment_link(
            order_id=order_id,
            amount_inr=total_amount,
            customer_phone=contact_num,
            description=f"PrintBot Order {order_id} ({page_count} pgs, {copies} cps)"
        )

        if not pay_res.get("success") or not pay_res.get("payment_url"):
            customer.bot_state = "WAITING_FOR_PAYMENT"
            db.commit()
            await self._send_message(
                customer,
                "⚠️ Payment is temporarily unavailable for this order. "
                "The shop administrator must configure Razorpay credentials before payments can be accepted."
            )
            return

        payment_url = pay_res["payment_url"]

        customer.active_order_id = order_id
        customer.bot_state = "WAITING_FOR_PAYMENT"
        flag_modified(customer, "state_data")
        db.commit()

        summary_text = (
            f"🧾 *ORDER SUMMARY*\n\n"
            f"🆔 *Order:* #{order_id}\n"
            f"📄 *File:* {filename}\n"
            f"📑 *Pages:* {page_count}\n"
            f"👥 *Copies:* {copies}\n"
            f"📐 *Paper:* {paper_size}\n"
            f"🎨 *Print:* {'Color' if color_mode.upper() == 'COLOR' else 'B&W'}\n"
            f"📄 *Sides:* {'Double-sided' if sides == 'double' else 'Single-sided'}\n\n"
            f"💰 *Total:* ₹{total_amount:.2f}"
        )

        await self._send_payment_msg(customer, summary_text, payment_url, f"₹{total_amount:.2f}")

    async def _handle_global_cancel(self, db: Session, customer: Customer):
        customer.bot_state = "IDLE"
        customer.state_data = {}
        flag_modified(customer, "state_data")
        db.commit()
        await self._send_message(
            customer,
            "❌ Order configuration cancelled.\n\nSend a document anytime to start a new print order."
        )

    async def _handle_global_restart(self, db: Session, customer: Customer):
        customer.bot_state = "WAITING_FOR_FILE"
        customer.state_data = {}
        flag_modified(customer, "state_data")
        db.commit()
        await self._send_message(
            customer,
            "🔄 Conversation reset. Send your document (PDF, Word, JPG, PNG) to begin."
        )

    async def _handle_global_status(self, db: Session, customer: Customer):
        latest_order = db.query(Order).filter(Order.customer_id == customer.id).order_by(Order.created_at.desc()).first()
        if not latest_order:
            await self._send_message(customer, "ℹ️ You don't have any active print orders yet. Send a document to start!")
            return

        status_text = (
            f"📊 *Order Status #{latest_order.id}*\n\n"
            f"📄 File: {latest_order.original_file_name}\n"
            f"💳 Payment: *{latest_order.payment_status}*\n"
            f"🖨️ Status: *{latest_order.current_state}*\n"
            f"📅 Date: {latest_order.created_at.strftime('%Y-%m-%d %H:%M')}"
        )
        await self._send_message(customer, status_text)

    async def _handle_global_help(self, db: Session, customer: Customer):
        help_text = (
            "🤖 *PrintBot Help & Commands*\n\n"
            "• Upload any *PDF, DOC, DOCX, JPG, PNG* file to start printing.\n"
            "• Type *STATUS* to check your latest order progress.\n"
            "• Type *CANCEL* to cancel your current order configuration.\n"
            "• Type *RESTART* to reset the conversation.\n\n"
            f"📞 Need support? Call us at {settings.BUSINESS_PHONE}."
        )
        await self._send_message(customer, help_text)

bot_state_machine = BotStateMachine()
