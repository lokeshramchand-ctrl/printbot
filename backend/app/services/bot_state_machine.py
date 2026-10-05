import asyncio
import logging
import mimetypes
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from pymongo.errors import DuplicateKeyError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.config import settings
from app.models.customer import Customer
from app.models.history import OrderStatusHistory
from app.models.order import Order
from app.models.payment import Payment
from app.models.webhook_event import WebhookEvent
from app.services import messenger, payment_service
from app.services.document_service import document_service
from app.services.pricing_service import pricing_service
from app.services.serial_service import allocate_order_id
from app.services.telegram_service import telegram_service
from app.services.whatsapp_service import whatsapp_service
from app.utils.helpers import escape_markdown, sanitize_filename
from app.utils.page_ranges import PageRangeError, looks_like_page_range, parse_page_range

logger = logging.getLogger("bot_state_machine")

DRAFT_STATES = ("ASK_COPIES", "ASK_COLOR", "ASK_PAPER_SIZE", "ASK_PAGES", "ASK_PAGE_RANGE", "ASK_SIDES")

_BW_WORDS = {"bw", "b&w", "b/w", "b-w", "black", "blackandwhite", "black&white", "mono", "gray", "grey", "blackwhite"}
_COLOR_WORDS = {"color", "colour", "colored", "coloured", "colors", "colours"}
_SINGLE_WORDS = {"single", "1", "onesided", "one-sided", "single-sided", "singlesided", "1sided", "oneside"}
_DOUBLE_WORDS = {"double", "2", "twosided", "two-sided", "double-sided", "doublesided", "2sided", "bothsides", "duplex"}


def _norm(text: str) -> str:
    """Lowercase and drop spaces/emoji so 'Black & White 🖤' == 'black&white'."""
    return re.sub(r"[^a-z0-9&/\-_]", "", (text or "").lower())


# --- Pure input parsers (unit-tested; return None when input is not understood) ---

def parse_copies(text: str) -> Optional[int]:
    """'COPIES_2' / '12' / '3 copies' -> int. The allowed range is validated by the caller."""
    match = re.fullmatch(r"copies_(\d{1,4})", (text or "").strip().lower())
    if match:
        return int(match.group(1))
    match = re.fullmatch(r"\s*(\d{1,4})\s*(?:x|cop(?:y|ies))?\s*", (text or "").lower())
    return int(match.group(1)) if match else None


def parse_color(text: str) -> Optional[str]:
    upper = (text or "").strip().upper()
    if upper == "COLOR_BW":
        return "BW"
    if upper == "COLOR_COLOR":
        return "Color"
    n = _norm(text)
    if n in _BW_WORDS:
        return "BW"
    if n in _COLOR_WORDS:
        return "Color"
    return None


def parse_paper(text: str) -> Optional[str]:
    n = _norm(text).replace("paper_", "").replace("paper", "")
    return {"a4": "A4", "a3": "A3", "letter": "Letter"}.get(n)


def parse_pages_choice(text: str) -> Optional[str]:
    """Returns 'ALL', 'SPECIFIC' or None."""
    n = _norm(text)
    if n in ("pages_all", "all", "allpages", "1", "everything"):
        return "ALL"
    if n in ("pages_specific", "specific", "specificpages", "2", "custom", "range", "somepages"):
        return "SPECIFIC"
    return None


def parse_sides(text: str) -> Optional[str]:
    n = _norm(text)
    if n == "sides_single" or n in _SINGLE_WORDS:
        return "single"
    if n == "sides_double" or n in _DOUBLE_WORDS:
        return "double"
    return None


class BotStateMachine:
    """Multi-channel conversational state machine (WhatsApp + Telegram)."""

    def __init__(self):
        self._chat_locks: Dict[str, asyncio.Lock] = {}

    def _lock_for(self, key: str) -> asyncio.Lock:
        lock = self._chat_locks.get(key)
        if lock is None:
            lock = self._chat_locks[key] = asyncio.Lock()
        return lock

    # --- Outbound helpers ---

    @staticmethod
    def _md(customer: Customer, text: str) -> str:
        """Escape user-supplied text (filenames) for Telegram's Markdown; WhatsApp needs none."""
        return escape_markdown(text) if customer.channel == "TELEGRAM" else text

    async def _send_message(self, customer: Customer, text: str):
        await messenger.send_message(customer, text)

    async def _send_buttons(self, customer: Customer, text: str, buttons: List[Tuple[str, str]]):
        await messenger.send_buttons(customer, text, buttons)

    @staticmethod
    def _set_state(db: Session, customer: Customer, state: str, **data: Any) -> Dict[str, Any]:
        """Move to ``state`` merging ``data`` into state_data (reassign + flag_modified for the JSON column)."""
        state_data = dict(customer.state_data or {})
        state_data.update(data)
        customer.state_data = state_data
        customer.bot_state = state
        flag_modified(customer, "state_data")
        db.commit()
        return state_data

    @staticmethod
    def _reset(db: Session, customer: Customer, state: str):
        customer.state_data = {}
        customer.active_order_id = None
        customer.bot_state = state
        flag_modified(customer, "state_data")
        db.commit()

    # --- Inbound WhatsApp ---

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
            msg_id = msg.get("id")
            msg_type = msg.get("type")
            contact_name = contacts[0].get("profile", {}).get("name") if contacts else "Customer"
            if not from_phone:
                return

            if msg_id and not self._claim_event(db, f"wa-{msg_id}", "WHATSAPP", msg_type or "message"):
                return  # Meta retries webhooks; never process the same message twice.

            await whatsapp_service.mark_message_as_read(msg_id)

            async with self._lock_for(f"wa:{from_phone}"):
                customer = db.query(Customer).filter(Customer.whatsapp_number == from_phone).first()
                if not customer:
                    customer = Customer(channel="WHATSAPP", whatsapp_number=from_phone,
                                        display_name=contact_name, bot_state="IDLE", state_data={})
                    db.add(customer)
                    db.commit()
                    db.refresh(customer)

                text_body, media_id = "", None
                if msg_type == "text":
                    text_body = msg.get("text", {}).get("body", "").strip()
                elif msg_type == "interactive":
                    interactive = msg.get("interactive", {})
                    reply = interactive.get("button_reply") or interactive.get("list_reply") or {}
                    # Prefer the stable button id (COPIES_2, SIDES_DOUBLE...) over the display title.
                    text_body = (reply.get("id") or reply.get("title") or "").strip()
                elif msg_type in ("document", "image"):
                    media_obj = msg.get(msg_type, {})
                    media_id = media_obj.get("id")
                    text_body = self._filename_for(media_obj.get("filename"), media_obj.get("mime_type"), msg_type)

                await self._process_state_transition(db, customer, text_body, media_id, msg_type, msg)
        except Exception:
            logger.exception("Error handling WhatsApp inbound message")

    # --- Inbound Telegram ---

    async def handle_telegram_update(self, db: Session, update: Dict[str, Any]):
        """Entry point for incoming Telegram updates (polling or webhook)."""
        try:
            message = update.get("message")
            callback_query = update.get("callback_query")
            file_size = 0
            media_id = None

            if callback_query:
                chat_id = str((callback_query.get("message") or {}).get("chat", {}).get("id"))
                from_name = callback_query.get("from", {}).get("first_name", "Telegram User")
                text_body = (callback_query.get("data") or "").strip()
                msg_type = "button_callback"
            elif message:
                chat_id = str(message.get("chat", {}).get("id"))
                from_name = message.get("from", {}).get("first_name", "Telegram User")
                text_body = (message.get("text") or "").strip()
                msg_type = "text"
                if "document" in message:
                    doc = message["document"]
                    media_id = doc.get("file_id")
                    file_size = doc.get("file_size") or 0
                    text_body = self._filename_for(doc.get("file_name"), doc.get("mime_type"), "document")
                    msg_type = "document"
                elif "photo" in message:
                    photo = message["photo"][-1]  # highest resolution
                    media_id = photo.get("file_id")
                    file_size = photo.get("file_size") or 0
                    text_body = "photo.jpg"
                    msg_type = "image"
            else:
                return

            if not chat_id or chat_id == "None":
                return

            update_id = update.get("update_id")
            if update_id is not None and not self._claim_event(db, f"tg-{update_id}", "TELEGRAM", msg_type):
                return  # already handled (poller restart / webhook retry)

            if callback_query:
                # Stop the button's loading spinner immediately.
                await telegram_service.answer_callback_query(callback_query.get("id"))

            async with self._lock_for(f"tg:{chat_id}"):
                customer = db.query(Customer).filter(Customer.telegram_chat_id == chat_id).first()
                if not customer:
                    customer = Customer(channel="TELEGRAM", telegram_chat_id=chat_id,
                                        whatsapp_number=f"tg_{chat_id}", display_name=from_name,
                                        bot_state="IDLE", state_data={})
                    db.add(customer)
                    db.commit()
                    db.refresh(customer)
                await self._process_state_transition(
                    db, customer, text_body, media_id, msg_type, update, file_size)
        except Exception:
            logger.exception("Error handling Telegram update")

    @staticmethod
    def _claim_event(db: Session, event_id: str, provider: str, event_type: str) -> bool:
        """Record an inbound event id; returns False if it was already seen (idempotency)."""
        try:
            db.add(WebhookEvent(event_id=event_id, provider=provider,
                                event_type=event_type or "message", processed=True))
            db.commit()
            return True
        except DuplicateKeyError:
            return False

    @staticmethod
    def _filename_for(name: Optional[str], mime: Optional[str], kind: str) -> str:
        if name:
            return name
        ext = (mimetypes.guess_extension(mime or "") or "").lstrip(".")
        ext = {"jpe": "jpg"}.get(ext, ext) or ("jpg" if kind == "image" else "pdf")
        return f"{kind}.{ext}"

    # --- Router ---

    async def _process_state_transition(
        self, db: Session, customer: Customer, text_body: str, media_id: Optional[str],
        msg_type: str, raw_obj: Dict[str, Any], file_size: int = 0,
    ):
        text_body = text_body or ""
        cmd = text_body.strip().upper()
        if cmd.startswith("/"):
            cmd = cmd.split()[0].split("@")[0]  # "/start@printbot arg" -> "/START"

        if cmd in ("CANCEL", "STOP", "CANCEL_ORDER", "/CANCEL"):
            await self._handle_global_cancel(db, customer)
            return
        if cmd in ("RESTART", "RESET", "/START", "/RESTART"):
            await self._handle_global_restart(db, customer)
            return
        if cmd in ("STATUS", "/STATUS"):
            await self._handle_global_status(db, customer)
            return
        if cmd in ("HELP", "/HELP"):
            await self._handle_global_help(db, customer)
            return
        if cmd.startswith("DEMO_PAY_"):
            await self._handle_demo_pay(db, customer, text_body.strip()[len("DEMO_PAY_"):])
            return
        if cmd == "RETRY_PAYMENT":
            await self._handle_retry_payment(db, customer)
            return

        state = customer.bot_state
        is_file = msg_type in ("document", "image")

        if state in ("IDLE", "WAITING_FOR_FILE") or (state in DRAFT_STATES and is_file):
            if is_file:
                await self._process_file_upload(db, customer, media_id, text_body, file_size)
            elif state == "IDLE":
                await self._send_greeting(db, customer)
            else:
                await self._send_message(
                    customer, "📄 Please send your PDF, Word document (DOC/DOCX), or image (JPG/PNG) to begin printing.")
        elif state == "ASK_COPIES":
            await self._handle_copies_input(db, customer, text_body)
        elif state == "ASK_COLOR":
            await self._handle_color_input(db, customer, text_body)
        elif state == "ASK_PAPER_SIZE":
            await self._handle_paper_size_input(db, customer, text_body)
        elif state == "ASK_PAGES":
            await self._handle_pages_input(db, customer, text_body)
        elif state == "ASK_PAGE_RANGE":
            await self._handle_page_range_input(db, customer, text_body)
        elif state == "ASK_SIDES":
            await self._handle_sides_input(db, customer, text_body)
        elif state == "WAITING_FOR_PAYMENT":
            await self._handle_waiting_for_payment(db, customer)
        else:
            await self._send_greeting(db, customer)

    # --- Greeting / upload ---

    async def _send_greeting(self, db: Session, customer: Customer):
        self._reset(db, customer, "WAITING_FOR_FILE")
        await self._send_message(
            customer,
            f"👋 Welcome to *{settings.BUSINESS_NAME}*!\n\n"
            "I can print your documents directly.\n\n"
            "📄 Send me your PDF, Word document (DOC/DOCX), JPG or PNG to get started.")

    async def _process_file_upload(self, db: Session, customer: Customer, media_id: Optional[str],
                                   filename: str, file_size: int = 0):
        if not document_service.is_supported(filename):
            await self._send_message(
                customer,
                "❌ *Unsupported file type.*\n\nPlease send:\n📄 PDF (.pdf)\n📝 Word (.doc, .docx)\n"
                "🖼️ Image (.jpg, .jpeg, .png)")
            return

        max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
        if file_size and file_size > max_bytes:
            await self._send_message(customer, f"❌ That file is too large. The limit is {settings.MAX_FILE_SIZE_MB} MB.")
            return

        order_id = allocate_order_id(db)
        raw_path = os.path.join(settings.STORAGE_DIR, "uploads", f"{order_id}_{sanitize_filename(filename)}")

        await self._send_message(customer, "⏳ Downloading and processing your file...")
        if customer.channel == "TELEGRAM":
            ok = await telegram_service.download_incoming_file(media_id, raw_path)
        else:
            ok = await whatsapp_service.download_incoming_media(media_id, raw_path)
        if not ok:
            await self._send_message(customer, "❌ Could not download file. Please try sending the document again.")
            return

        if os.path.getsize(raw_path) > max_bytes:
            os.remove(raw_path)
            await self._send_message(customer, f"❌ That file is too large. The limit is {settings.MAX_FILE_SIZE_MB} MB.")
            return

        proc = document_service.process_file(raw_path, order_id, filename)
        if not proc.get("success"):
            await self._send_message(
                customer, f"❌ {proc.get('error', 'Could not process document.')}\n\nPlease try uploading again.")
            return

        self._reset(db, customer, "ASK_COPIES")
        self._set_state(
            db, customer, "ASK_COPIES",
            order_id=order_id, filename=filename, raw_path=raw_path, pdf_path=proc["pdf_path"],
            page_count=proc["page_count"], file_type=proc["file_type"], file_size=proc["file_size"],
            pages_to_print="all", selected_pages=proc["page_count"], print_pdf_path=proc["pdf_path"],
        )
        await self._ask_copies(customer, filename, proc["page_count"])

    # --- Prompts ---

    async def _ask_copies(self, customer: Customer, filename: Optional[str] = None, page_count: Optional[int] = None):
        head = ""
        if filename:
            head = (f"✅ *File received!*\n\n📄 File: *{self._md(customer, filename)}*\n"
                    f"📑 Pages: *{page_count}*\n\n")
        buttons = [("COPIES_1", "1️⃣ 1 copy"), ("COPIES_2", "2️⃣ 2 copies"), ("COPIES_3", "3️⃣ 3 copies")]
        if customer.channel == "TELEGRAM":
            buttons.append(("COPIES_CUSTOM", "✏️ Other number"))
        await self._send_buttons(customer, head + "Choose the number of copies (or just type a number):", buttons)

    async def _ask_color(self, customer: Customer):
        await self._send_buttons(customer, "Choose printing type:\n\n🖤 Black & White\n🌈 Color",
                                 [("COLOR_BW", "🖤 B&W"), ("COLOR_COLOR", "🌈 Color")])

    async def _ask_paper(self, customer: Customer):
        await self._send_buttons(customer, "Choose paper size:",
                                 [("PAPER_A4", "📄 A4"), ("PAPER_A3", "📄 A3"), ("PAPER_LETTER", "📄 Letter")])

    async def _ask_pages(self, customer: Customer):
        await self._send_buttons(customer, "Which pages should be printed?",
                                 [("PAGES_ALL", "1️⃣ All pages"), ("PAGES_SPECIFIC", "2️⃣ Specific pages")])

    async def _ask_page_range(self, customer: Customer, page_count: int):
        await self._send_message(
            customer,
            f"✏️ Type the pages to print (your document has *{page_count}* page{'s' if page_count != 1 else ''}).\n\n"
            "Examples: 1-3  or  5  or  1-3, 7, 10-12")

    async def _ask_sides(self, customer: Customer):
        await self._send_buttons(customer, "Do you want:\n\n1️⃣ Single-sided\n2️⃣ Double-sided",
                                 [("SIDES_SINGLE", "1️⃣ Single-sided"), ("SIDES_DOUBLE", "2️⃣ Double-sided")])

    # --- Step handlers (strict: unknown input re-asks instead of silently defaulting) ---

    async def _handle_copies_input(self, db: Session, customer: Customer, text: str):
        if text.strip().upper() == "COPIES_CUSTOM":
            await self._send_message(customer, f"✏️ Type the number of copies (1-{settings.MAX_COPIES}):")
            return
        copies = parse_copies(text)
        if copies is None:
            await self._send_message(customer, "🤔 I didn't get that. Tap a button or type a number of copies, e.g. 12.")
            await self._ask_copies(customer)
            return
        if not 1 <= copies <= settings.MAX_COPIES:
            await self._send_message(customer, f"⚠️ Copies must be between 1 and {settings.MAX_COPIES}.")
            return
        self._set_state(db, customer, "ASK_COLOR", copies=copies)
        await self._ask_color(customer)

    async def _handle_color_input(self, db: Session, customer: Customer, text: str):
        color = parse_color(text)
        if color is None:
            await self._send_message(customer, "🤔 Please choose *B&W* or *Color* using the buttons.")
            await self._ask_color(customer)
            return
        self._set_state(db, customer, "ASK_PAPER_SIZE", color_mode=color)
        await self._ask_paper(customer)

    async def _handle_paper_size_input(self, db: Session, customer: Customer, text: str):
        paper = parse_paper(text)
        if paper is None:
            await self._send_message(customer, "🤔 Please choose *A4*, *A3* or *Letter* using the buttons.")
            await self._ask_paper(customer)
            return
        self._set_state(db, customer, "ASK_PAGES", paper_size=paper)
        await self._ask_pages(customer)

    async def _handle_pages_input(self, db: Session, customer: Customer, text: str):
        data = customer.state_data or {}
        total = int(data.get("page_count", 1))
        choice = parse_pages_choice(text)

        if choice is None and looks_like_page_range(text):
            # Customer typed a range straight away ("1-3,5") instead of tapping the button.
            await self._handle_page_range_input(db, customer, text)
            return
        if choice is None:
            await self._send_message(customer, "🤔 Please choose *All pages* or *Specific pages* using the buttons.")
            await self._ask_pages(customer)
            return
        if choice == "ALL" or total == 1:
            self._set_state(db, customer, "ASK_SIDES", pages_to_print="all", selected_pages=total,
                            print_pdf_path=data.get("pdf_path"))
            await self._ask_sides(customer)
            return
        self._set_state(db, customer, "ASK_PAGE_RANGE")
        await self._ask_page_range(customer, total)

    async def _handle_page_range_input(self, db: Session, customer: Customer, text: str):
        data = customer.state_data or {}
        total = int(data.get("page_count", 1))
        if _norm(text) in ("all", "allpages", "pages_all"):
            self._set_state(db, customer, "ASK_SIDES", pages_to_print="all", selected_pages=total,
                            print_pdf_path=data.get("pdf_path"))
            await self._ask_sides(customer)
            return
        try:
            spec, pages = parse_page_range(text, total)
        except PageRangeError as e:
            await self._send_message(customer, f"⚠️ {e}")
            await self._ask_page_range(customer, total)
            return

        if len(pages) == total:
            self._set_state(db, customer, "ASK_SIDES", pages_to_print="all", selected_pages=total,
                            print_pdf_path=data.get("pdf_path"))
        else:
            source = data["pdf_path"]
            selected_path = os.path.join(os.path.dirname(source), "selected.pdf")
            try:
                document_service.extract_pages(source, selected_path, pages)
            except Exception:
                logger.exception("Page extraction failed")
                await self._send_message(customer, "❌ Couldn't prepare those pages. Please try again.")
                return
            self._set_state(db, customer, "ASK_SIDES", pages_to_print=spec, selected_pages=len(pages),
                            print_pdf_path=selected_path)
        await self._ask_sides(customer)

    async def _handle_sides_input(self, db: Session, customer: Customer, text: str):
        sides = parse_sides(text)
        if sides is None:
            await self._send_message(customer, "🤔 Please choose *Single-sided* or *Double-sided* using the buttons.")
            await self._ask_sides(customer)
            return
        state_data = self._set_state(db, customer, "ASK_SIDES", sides=sides)
        await self._create_order(db, customer, state_data)

    # --- Order creation + payment ---

    async def _create_order(self, db: Session, customer: Customer, d: Dict[str, Any]):
        order_id = d["order_id"]
        pages = int(d.get("selected_pages") or d.get("page_count", 1))
        copies, paper = d.get("copies", 1), d.get("paper_size", "A4")
        color, sides = d.get("color_mode", "BW"), d["sides"]

        price = pricing_service.calculate_price(db, paper, color, sides, pages, copies)
        total = price["total_amount"]

        order = Order(
            id=order_id, customer_id=customer.id, channel=customer.channel,
            original_file_name=d.get("filename"), stored_file_path=d.get("raw_path"),
            printable_pdf_path=d.get("print_pdf_path") or d.get("pdf_path"),
            file_type=d.get("file_type", "PDF"), file_size_bytes=d.get("file_size", 0),
            total_pages=pages, copies=copies, paper_size=paper, color_mode=color, sides=sides,
            pages_to_print=d.get("pages_to_print", "all"),
            rate_per_page=price["rate_per_page"], subtotal_amount=price["subtotal"],
            additional_charges=price["additional_charge"], total_amount=total,
            payment_status="PENDING", current_state="PAYMENT_PENDING",
        )
        db.add(order)
        db.add(OrderStatusHistory(order_id=order_id, from_status="CONFIGURING", to_status="PAYMENT_PENDING",
                                  trigger_source="BOT", notes=f"Order calculated: ₹{total}"))
        customer.active_order_id = order_id
        self._set_state(db, customer, "WAITING_FOR_PAYMENT")
        db.refresh(order)

        description = f"PrintBot Order {order_id} ({pages} pgs, {copies} cps)"
        checkout = await payment_service.create_checkout(db, order, customer, description)
        if not checkout.get("success"):
            logger.error(f"Checkout creation failed for {order_id}: {checkout.get('error')}")
            await self._send_buttons(
                customer,
                "⚠️ Payment couldn't be started right now. Your order is saved - tap *Retry* in a moment, or cancel.",
                [("RETRY_PAYMENT", "🔁 Retry payment"), ("CANCEL_ORDER", "❌ Cancel Order")])
            return
        await self._send_payment_prompt(customer, order, checkout.get("payment_url"))

    def _summary_text(self, customer: Customer, order: Order) -> str:
        pages_line = (f"{order.total_pages}" if order.pages_to_print in (None, "all")
                      else f"{order.total_pages} (pages {order.pages_to_print})")
        return (
            f"🧾 *ORDER SUMMARY*\n\n"
            f"🆔 *Order:* #{order.id}\n"
            f"📄 *File:* {self._md(customer, order.original_file_name or '')}\n"
            f"📑 *Pages:* {pages_line}\n"
            f"👥 *Copies:* {order.copies}\n"
            f"📐 *Paper:* {order.paper_size}\n"
            f"🎨 *Print:* {'Color' if (order.color_mode or '').upper() == 'COLOR' else 'B&W'}\n"
            f"📄 *Sides:* {'Double-sided' if order.sides == 'double' else 'Single-sided'}\n\n"
            f"💰 *Total:* ₹{order.total_amount:.2f}"
        )

    async def _send_payment_prompt(self, customer: Customer, order: Order, payment_url: Optional[str]):
        await messenger.send_payment_prompt(
            customer, self._summary_text(customer, order), f"₹{order.total_amount:.2f}", order.id, payment_url)

    def _active_order(self, db: Session, customer: Customer) -> Optional[Order]:
        if not customer.active_order_id:
            return None
        return db.query(Order).filter(Order.id == customer.active_order_id).first()

    async def _handle_waiting_for_payment(self, db: Session, customer: Customer):
        order = self._active_order(db, customer)
        if order is None or order.current_state != "PAYMENT_PENDING":
            # Cancelled/paid elsewhere (admin, webhook): never leave the customer stuck.
            await self._send_greeting(db, customer)
            return
        link = db.query(Payment).filter(Payment.order_id == order.id, Payment.status == "CREATED").first()
        if link is None:
            await self._handle_retry_payment(db, customer)
            return
        await self._send_payment_prompt(customer, order, link.razorpay_payment_link_url)

    async def _handle_retry_payment(self, db: Session, customer: Customer):
        order = self._active_order(db, customer)
        if order is None or order.current_state != "PAYMENT_PENDING":
            await self._send_message(
                customer, "ℹ️ There's no order waiting for payment. Send a document to start a new one.")
            return
        existing = db.query(Payment).filter(Payment.order_id == order.id, Payment.status == "CREATED").first()
        if existing:
            await self._send_payment_prompt(customer, order, existing.razorpay_payment_link_url)
            return
        checkout = await payment_service.create_checkout(
            db, order, customer, f"PrintBot Order {order.id} ({order.total_pages} pgs, {order.copies} cps)")
        if not checkout.get("success"):
            await self._send_buttons(customer, "⚠️ Payment is still unavailable. Please try again shortly.",
                                     [("RETRY_PAYMENT", "🔁 Retry payment"), ("CANCEL_ORDER", "❌ Cancel Order")])
            return
        await self._send_payment_prompt(customer, order, checkout.get("payment_url"))

    async def _handle_demo_pay(self, db: Session, customer: Customer, order_id: str):
        if not payment_service.is_demo_mode():
            await self._send_message(customer, "⚠️ Demo payments are disabled.")
            return
        order = db.query(Order).filter(Order.id == order_id.upper()).first()
        if order is None or order.customer_id != customer.id:
            await self._send_message(customer, "⚠️ I couldn't find that order.")
            return
        result = await payment_service.confirm_payment(db, order.id, source="BOT_DEMO", method="demo")
        if result["status"] == "already_processed":
            await self._send_message(customer, f"ℹ️ Order *#{order.id}* is already paid.")
        elif result["status"] == "not_payable":
            await self._send_message(customer, f"⚠️ Order *#{order.id}* can no longer be paid ({result.get('state')}).")

    # --- Global commands ---

    async def _abandon_active_order(self, db: Session, customer: Customer) -> Optional[str]:
        """Cancel the unpaid order the customer is paying for; returns its id if cancelled."""
        if customer.bot_state != "WAITING_FOR_PAYMENT":
            return None
        order = self._active_order(db, customer)
        if order and await payment_service.cancel_order(db, order, source="BOT", notes="Cancelled by customer"):
            return order.id
        return None

    async def _handle_global_cancel(self, db: Session, customer: Customer):
        cancelled_id = await self._abandon_active_order(db, customer)
        self._reset(db, customer, "IDLE")
        extra = f" Order #{cancelled_id} was cancelled." if cancelled_id else ""
        await self._send_message(customer, f"❌ Cancelled.{extra}\n\nSend a document anytime to start a new print order.")

    async def _handle_global_restart(self, db: Session, customer: Customer):
        await self._abandon_active_order(db, customer)
        self._reset(db, customer, "WAITING_FOR_FILE")
        await self._send_message(customer, "🔄 Conversation reset. Send your document (PDF, Word, JPG, PNG) to begin.")

    async def _handle_global_status(self, db: Session, customer: Customer):
        order = db.query(Order).filter(Order.customer_id == customer.id).order_by(Order.created_at.desc()).first()
        if not order:
            await self._send_message(customer, "ℹ️ You don't have any print orders yet. Send a document to start!")
            return
        serial = (f"\n🔑 Pickup code: {order.pickup_code}" if order.pickup_code else "") + \
            (f"\n🔖 Reference: {order.print_serial}" if order.print_serial else "")
        await self._send_message(
            customer,
            f"📊 *Order Status #{order.id}*\n\n"
            f"📄 File: {self._md(customer, order.original_file_name or '')}\n"
            f"💳 Payment: *{order.payment_status}*\n"
            f"🖨️ Status: *{order.current_state}*{serial}\n"
            f"📅 Date: {order.created_at.strftime('%Y-%m-%d %H:%M')}")

    async def _handle_global_help(self, db: Session, customer: Customer):
        await self._send_message(
            customer,
            "🤖 *PrintBot Help & Commands*\n\n"
            "• Upload any *PDF, DOC, DOCX, JPG, PNG* file to start printing.\n"
            "• Type *STATUS* to check your latest order.\n"
            "• Type *CANCEL* to cancel your current order.\n"
            "• Type *RESTART* to reset the conversation.\n\n"
            f"📞 Need support? Call us at {settings.BUSINESS_PHONE}.")


bot_state_machine = BotStateMachine()
