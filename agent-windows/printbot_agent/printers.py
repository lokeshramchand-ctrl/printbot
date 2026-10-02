"""Windows printer discovery and silent PDF printing (PyMuPDF render -> GDI).

Pages are rasterised at the printer's resolution (capped at 300 dpi) and drawn through the
driver, so duplex, colour and paper size are applied per job via the DEVMODE.
"""
import io
from typing import List

from .api import AgentJob, ReportedPrinter

try:  # pywin32 only exists on Windows; tests on other platforms never reach the print path
    import win32con
    import win32gui
    import win32print
    import win32ui
    from PIL import ImageWin
except ImportError:  # pragma: no cover
    win32print = None

DM_PAPERSIZE, DM_DUPLEX, DM_COLOR = 0x2, 0x1000, 0x800
PAPER_CODES = {"A3": 8, "A4": 9, "A5": 11, "LETTER": 1, "LEGAL": 5}
# paused / error / paper jam / no paper / offline / not available
BAD_STATUS = 0x1 | 0x2 | 0x8 | 0x10 | 0x80 | 0x400 | 0x1000
DC_COLORDEVICE = 32
MAX_DPI = 300


class PrintError(Exception):
    pass


def _require_win32():
    if win32print is None:
        raise PrintError("Windows printing needs pywin32 (Windows only)")


def discover(color_default: bool = True) -> List[ReportedPrinter]:
    _require_win32()
    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    out = []
    for p in win32print.EnumPrinters(flags, None, 2):
        name = p["pPrinterName"]
        try:
            color = bool(win32print.DeviceCapabilities(name, p["pPortName"], DC_COLORDEVICE))
        except Exception:
            color = color_default
        out.append(ReportedPrinter(
            name=name, model=p.get("pDriverName"), color=color,
            paper_sizes=["A4", "Letter"],
            state="error" if p.get("Status", 0) & BAD_STATUS else "ok"))
    return out


def _devmode(name: str, job: AgentJob):
    h = win32print.OpenPrinter(name)
    try:
        dm = win32print.GetPrinter(h, 2)["pDevMode"]
    finally:
        win32print.ClosePrinter(h)
    if dm is None:
        raise PrintError(f'Printer "{name}" has no settings available')
    code = PAPER_CODES.get(job.paper_size.upper())
    if code:
        dm.PaperSize = code
        dm.Fields |= DM_PAPERSIZE
    dm.Duplex = 2 if job.duplex else 1  # 2 = long edge
    dm.Fields |= DM_DUPLEX
    dm.Color = 2 if job.color else 1
    dm.Fields |= DM_COLOR
    return dm


def print_pdf(job: AgentJob, pdf: bytes) -> None:
    _require_win32()
    import pymupdf
    from PIL import Image

    if not any(p.name == job.printer_name for p in discover()):
        raise PrintError(f'Printer "{job.printer_name}" is not installed on this PC')
    try:
        doc = pymupdf.open(stream=pdf, filetype="pdf")
    except Exception as e:
        raise PrintError(f"Unreadable PDF: {e}") from e
    if doc.page_count == 0:
        raise PrintError("PDF has no pages")

    dm = _devmode(job.printer_name, job)
    hdc = win32gui.CreateDC("WINSPOOL", job.printer_name, dm)
    dc = win32ui.CreateDCFromHandle(hdc)
    try:
        width = dc.GetDeviceCaps(win32con.HORZRES)
        height = dc.GetDeviceCaps(win32con.VERTRES)
        dpi = min(dc.GetDeviceCaps(win32con.LOGPIXELSX), MAX_DPI) or MAX_DPI
        # Copies are repeated documents: drivers disagree on honouring dmCopies/collation.
        for _ in range(max(job.copies, 1)):
            dc.StartDoc(job.label)
            try:
                for page in doc:
                    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csRGB if job.color else pymupdf.csGRAY)
                    img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
                    if (img.width > img.height) != (width > height):
                        img = img.rotate(90, expand=True)
                    # Fit the printable area, preserving aspect ratio.
                    scale = min(width / img.width, height / img.height)
                    w, h = int(img.width * scale), int(img.height * scale)
                    left, top = (width - w) // 2, (height - h) // 2
                    dc.StartPage()
                    ImageWin.Dib(img).draw(dc.GetHandleOutput(), (left, top, left + w, top + h))
                    dc.EndPage()
                dc.EndDoc()
            except Exception:
                dc.AbortDoc()
                raise
    except PrintError:
        raise
    except Exception as e:
        raise PrintError(f"Print failed: {e}") from e
    finally:
        dc.DeleteDC()
        doc.close()
