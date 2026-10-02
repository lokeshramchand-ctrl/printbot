"""Parsing of customer-typed page selections such as ``1-3, 5, 8-10``."""
import re
from typing import List, Optional, Tuple

_TOKEN = re.compile(r"^(\d{1,5})(?:\s*-\s*(\d{1,5}))?$")


class PageRangeError(ValueError):
    """Raised with a customer-friendly message when a page selection is invalid."""


def looks_like_page_range(text: str) -> bool:
    """True for input made only of digits, commas, dashes and spaces that contains a digit."""
    return bool(text) and bool(re.fullmatch(r"[\d,\-\s]+", text)) and any(c.isdigit() for c in text)


def parse_page_range(text: str, total_pages: int) -> Tuple[str, List[int]]:
    """Return ``(normalized_spec, sorted_unique_1_based_pages)``.

    ``"3, 1-2, 2"`` -> ``("1-3", [1, 2, 3])``. Raises ``PageRangeError`` on
    malformed input, reversed ranges or pages beyond the document.
    """
    cleaned = (text or "").replace(" ", "").strip(",")
    if not cleaned:
        raise PageRangeError("Please type the pages to print, e.g. 1-3, 5, 8-10.")

    pages: set[int] = set()
    for token in cleaned.split(","):
        match = _TOKEN.match(token)
        if not match:
            raise PageRangeError(f"I couldn't understand “{token}”. Use numbers and ranges like 1-3, 5, 8-10.")
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else start
        if start < 1 or end < 1:
            raise PageRangeError("Page numbers start at 1.")
        if end < start:
            raise PageRangeError(f"“{token}” is backwards - write it as {end}-{start}.")
        if end > total_pages:
            raise PageRangeError(f"Your document only has {total_pages} page{'s' if total_pages != 1 else ''}.")
        pages.update(range(start, end + 1))

    ordered = sorted(pages)
    return format_page_ranges(ordered), ordered


def format_page_ranges(pages: List[int]) -> str:
    """Compress ``[1, 2, 3, 5]`` into ``"1-3,5"``."""
    parts: List[str] = []
    start: Optional[int] = None
    prev: Optional[int] = None
    for page in pages:
        if start is None:
            start = prev = page
        elif page == prev + 1:
            prev = page
        else:
            parts.append(f"{start}-{prev}" if start != prev else str(start))
            start = prev = page
    if start is not None:
        parts.append(f"{start}-{prev}" if start != prev else str(start))
    return ",".join(parts)
