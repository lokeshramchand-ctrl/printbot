"""
Stamps a small, unobtrusive reference line onto every page of a generated
*printable* PDF — never the customer's original upload, which is left
completely untouched at Order.stored_file_path.

Why PyMuPDF (fitz) here: document_service already uses it to build the
printable.pdf and to count pages, so there's no new dependency, and
insert_text() draws directly into the existing page content stream
without resizing, rescaling, or re-flowing anything already on the page —
it just adds a thin strip of text inside the page's own margin.

The stamp answers the exact question a staff member has when they pick a
loose page off a stack: "whose order is this, and which page of how many?"
It shows:
  - the order's print serial (PB-YYYYMMDD-NNNNNN)
  - the print date
  - a short customer identifier (never a full phone number)
  - the page number within this document

Placement: bottom-center, ~10pt from the physical edge, in a small
grey font. That sits inside the unprintable margin most consumer and
office printers already reserve, so it does not compete with the
customer's own content and is not clipped by the printer.
"""
import logging
import os
from datetime import datetime
import fitz  # PyMuPDF

logger = logging.getLogger("pdf_stamp_service")

STAMP_FONT_SIZE = 6.5
STAMP_MARGIN_FROM_BOTTOM = 12  # points
STAMP_COLOR = (0.32, 0.32, 0.32)  # neutral dark grey — legible, unobtrusive


def build_stamp_text(serial: str, when: datetime, customer_label: str, page_num: int, total_pages: int) -> str:
    date_str = when.strftime("%Y-%m-%d")
    return f"{serial}  |  {date_str}  |  {customer_label}  |  Pg {page_num}/{total_pages}"


def stamp_printable_pdf(pdf_path: str, serial: str, customer_label: str, when: datetime = None) -> bool:
    """
    Opens the printable PDF in place and stamps every page with the
    serial/date/customer/page-number footer. Returns True on success.

    Idempotency is the caller's responsibility (Order.serial_stamped_at) —
    calling this twice on the same file would double-stamp it, so
    print_service only calls this once per order, the first time it enters
    the queue.
    """
    when = when or datetime.utcnow()
    try:
        doc = fitz.open(pdf_path)
        total_pages = len(doc)

        for i, page in enumerate(doc, start=1):
            rect = page.rect
            text = build_stamp_text(serial, when, customer_label, i, total_pages)

            # Draw at an explicit baseline, centered by measured width. (insert_textbox
            # silently draws nothing when its box is a hair too small for the page's
            # font metrics, which real-world PDFs trigger; insert_text always draws.)
            size = STAMP_FONT_SIZE
            width = fitz.get_text_length(text, fontname="helv", fontsize=size)
            max_width = rect.width - 20
            if width > max_width:
                size = size * max_width / width
                width = max_width
            origin = fitz.Point(rect.x0 + (rect.width - width) / 2, rect.y1 - STAMP_MARGIN_FROM_BOTTOM)
            page.insert_text(origin, text, fontsize=size, fontname="helv", color=STAMP_COLOR)

        # PyMuPDF refuses doc.save() back to the same path it was opened
        # from unless the save is incremental, and incremental saves have
        # sharper edge cases (they can't follow certain structural
        # changes and grow the file on every stamp). Saving to a sibling
        # temp file and atomically replacing the original sidesteps both
        # problems and guarantees the original file is never left
        # half-written if the process is killed mid-save.
        tmp_path = f"{pdf_path}.stamping.tmp"
        doc.save(tmp_path)
        doc.close()
        os.replace(tmp_path, pdf_path)
        return True
    except Exception as e:
        logger.exception(f"Failed to stamp print serial onto {pdf_path}: {str(e)}")
        return False


def customer_label_for(customer) -> str:
    """
    Builds a short, non-sensitive identifier for the stamp — never the
    customer's raw phone number or full chat ID. Uses the internal
    customer record id plus a channel initial, e.g. 'W-102' or 'T-57'.
    """
    if customer is None:
        return "GUEST"
    channel_initial = "W" if (customer.channel or "").upper().startswith("WHATS") else "T"
    return f"{channel_initial}-{customer.id}"
