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
from typing import Optional
import fitz  # PyMuPDF
from app.config import settings

logger = logging.getLogger("pdf_stamp_service")

STAMP_FONT_SIZE = 6.5
STAMP_MARGIN_FROM_BOTTOM = 12  # points
STAMP_COLOR = (0.32, 0.32, 0.32)  # neutral dark grey — legible, unobtrusive


def build_stamp_text(serial: str, when: datetime, customer_label: str, page_num: int, total_pages: int,
                     copy_num: int = 1, total_copies: int = 1, sheet_num: int = None,
                     total_sheets: int = None, side: str = None, blank: bool = False) -> str:
    """One stamp line. Copy and sheet/side parts only appear when they carry information:
    'Copy 2/3' when there are several copies, 'Sheet 2/3 B' on double-sided jobs (F=front, B=back)."""
    parts = [serial, when.strftime("%Y-%m-%d"), customer_label]
    if total_copies > 1:
        parts.append(f"Copy {copy_num}/{total_copies}")
    if sheet_num is not None:
        parts.append(f"Sheet {sheet_num}/{total_sheets} {side}")
    parts.append("Blank back" if blank else f"Pg {page_num}/{total_pages}")
    return "  |  ".join(parts)


def _draw_centered(page, y: float, text: str, size: float, fontname: str = "helv", color=(0, 0, 0)):
    """Draw text centred on the page at baseline y, shrinking to fit the page width."""
    width = fitz.get_text_length(text, fontname=fontname, fontsize=size)
    max_width = page.rect.width - 20
    if width > max_width:
        size = size * max_width / width
        width = max_width
    page.insert_text(fitz.Point(page.rect.x0 + (page.rect.width - width) / 2, y), text,
                     fontsize=size, fontname=fontname, color=color)


def _stamp_page(page, text: str):
    # Explicit baseline, centred by measured width. (insert_textbox silently draws nothing
    # when its box is a hair too small for the page's font metrics; insert_text always draws.)
    _draw_centered(page, page.rect.y1 - STAMP_MARGIN_FROM_BOTTOM, text, STAMP_FONT_SIZE, color=STAMP_COLOR)


def _add_cover_sheet(doc, size: fitz.Rect, pickup_code: str, serial: str, lines: list):
    page = doc.new_page(pno=-1, width=size.width, height=size.height)
    h = size.height
    _draw_centered(page, h * 0.22, "PICKUP CODE", 26, "helv", (0.35, 0.35, 0.35))
    _draw_centered(page, h * 0.40, pickup_code, 120, "hebo")
    page.draw_line((50, h * 0.45), (size.width - 50, h * 0.45), color=(0, 0, 0), width=1.5)
    y = h * 0.52
    for line in lines:
        _draw_centered(page, y, line, 16, "helv", (0.15, 0.15, 0.15))
        y += 26
    _draw_centered(page, y + 14, serial, 12, "helv", (0.35, 0.35, 0.35))
    _draw_centered(page, h - 40, "Cover sheet - remove before use", 9, "helv", (0.5, 0.5, 0.5))


def prepare_print_ready_pdf(pdf_path: str, serial: str, customer_label: str, when: datetime = None,
                            copies: int = 1, sides: str = "single", pickup_code: str = None,
                            cover_lines: list = None) -> Optional[int]:
    """
    Rewrites the printable PDF in place into exactly what comes out of the printer:
      - an optional cover sheet carrying the big pickup code (when ``cover_lines`` is given),
      - every copy written out in full (so each is stamped 'Copy n/m'), unless that would
        exceed MAX_EXPANDED_PAGES — then it is stamped once and the driver's copies option
        is kept,
      - on double-sided jobs, a stamped blank back page after any odd-length document or
        cover, so the next copy / the content always starts on a fresh sheet,
      - a stamp on every page: serial, date, customer, copy, sheet/side and page.

    Returns the number of copies baked into the PDF (copies, or 1 when not expanded),
    or None on failure. Failure leaves the original file untouched (atomic replace).
    Idempotency is the caller's responsibility (Order.serial_stamped_at).
    """
    when = when or datetime.utcnow()
    duplex = (sides or "").lower() == "double"
    copies = max(1, int(copies or 1))
    try:
        src = fitz.open(pdf_path)
        n = len(src)
        if n == 0:
            src.close()
            return None
        if n * copies > settings.MAX_EXPANDED_PAGES:
            copies = 1  # too big to expand; stamp once and let the driver do the copies
            baked = 1
            expanded = False
        else:
            baked = copies
            expanded = True
        copies_to_write = copies if expanded else 1
        label_copies = copies if expanded else 1
        total_sheets = (n + 1) // 2

        out = fitz.open()
        if cover_lines is not None and pickup_code:
            _add_cover_sheet(out, src[0].rect, pickup_code, serial, cover_lines)
            if duplex:
                out.new_page(pno=-1, width=src[0].rect.width, height=src[0].rect.height)

        for c in range(1, copies_to_write + 1):
            first = len(out)
            out.insert_pdf(src)
            for i in range(n):
                sheet = side = None
                if duplex:
                    sheet, side = i // 2 + 1, ("F" if i % 2 == 0 else "B")
                _stamp_page(out[first + i], build_stamp_text(
                    serial, when, customer_label, i + 1, n, c, label_copies, sheet, total_sheets, side))
            if duplex and n % 2 == 1 and c < copies_to_write:
                blank = out.new_page(pno=-1, width=src[-1].rect.width, height=src[-1].rect.height)
                _stamp_page(blank, build_stamp_text(
                    serial, when, customer_label, n, n, c, label_copies, total_sheets, total_sheets, "B", blank=True))

        # PyMuPDF refuses doc.save() back to the path it was opened from unless the save is
        # incremental (which has edge cases). Saving to a sibling temp file and atomically
        # replacing the original also guarantees it is never left half-written.
        # garbage=4 merges the duplicate objects created by expanding copies.
        tmp_path = f"{pdf_path}.stamping.tmp"
        out.save(tmp_path, garbage=4, deflate=True)
        out.close()
        src.close()
        os.replace(tmp_path, pdf_path)
        return baked
    except Exception as e:
        logger.exception(f"Failed to prepare print-ready PDF {pdf_path}: {str(e)}")
        return None


def stamp_printable_pdf(pdf_path: str, serial: str, customer_label: str, when: datetime = None, **kwargs) -> bool:
    """Stamp-only convenience wrapper (single copy, single-sided, no cover unless kwargs say so)."""
    return prepare_print_ready_pdf(pdf_path, serial, customer_label, when, **kwargs) is not None


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
