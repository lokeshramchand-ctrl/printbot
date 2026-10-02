import os
import shutil
import subprocess
import logging
import fitz  # PyMuPDF
from PIL import Image
from typing import Dict, Any, Tuple, Optional
from app.config import settings

logger = logging.getLogger("document_service")

SUPPORTED_EXTENSIONS = {
    "pdf": "PDF",
    "doc": "DOC",
    "docx": "DOCX",
    "jpg": "JPG",
    "jpeg": "JPEG",
    "png": "PNG"
}

SUPPORTED_MIME_TYPES = [
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "image/jpeg",
    "image/png"
]

class DocumentService:
    """Document processing pipeline for PDF, Word, and Images."""

    @staticmethod
    def is_supported(filename: str, mime_type: Optional[str] = None) -> bool:
        ext = filename.split(".")[-1].lower() if "." in filename else ""
        if ext in SUPPORTED_EXTENSIONS:
            return True
        if mime_type and mime_type.lower() in SUPPORTED_MIME_TYPES:
            return True
        return False

    @classmethod
    def process_file(cls, input_file_path: str, order_id: str, original_filename: str) -> Dict[str, Any]:
        """
        Processes an incoming uploaded file:
        1. Validates extension/type
        2. Converts DOC/DOCX or Image to PDF
        3. Validates and counts PDF pages using PyMuPDF
        4. Generates preview thumbnail for Admin UI
        """
        ext = original_filename.split(".")[-1].lower() if "." in original_filename else "bin"
        if not cls.is_supported(original_filename):
            return {
                "success": False,
                "error": "Unsupported file format. Please upload PDF, DOC, DOCX, JPG, or PNG."
            }

        file_size = os.path.getsize(input_file_path) if os.path.exists(input_file_path) else 0
        order_dir = os.path.join(settings.STORAGE_DIR, "processed", order_id)
        os.makedirs(order_dir, exist_ok=True)
        
        pdf_output_path = os.path.join(order_dir, "printable.pdf")
        thumbnail_output_path = os.path.join(settings.STORAGE_DIR, "previews", f"{order_id}_thumb.png")

        try:
            # Conversion step based on format
            if ext == "pdf":
                shutil.copyfile(input_file_path, pdf_output_path)
            elif ext in ("jpg", "jpeg", "png"):
                cls._convert_image_to_pdf(input_file_path, pdf_output_path)
            elif ext in ("doc", "docx"):
                success, err = cls._convert_word_to_pdf(input_file_path, order_dir)
                if not success:
                    return {"success": False, "error": err}
            else:
                return {"success": False, "error": "Unrecognized document format."}

            # PyMuPDF processing: Count pages and verify PDF validity
            page_count = cls._get_pdf_page_count_and_thumbnail(pdf_output_path, thumbnail_output_path)
            if page_count <= 0:
                return {"success": False, "error": "Corrupted or unreadable PDF document."}

            return {
                "success": True,
                "file_type": ext.upper(),
                "file_size": file_size,
                "page_count": page_count,
                "pdf_path": pdf_output_path,
                "thumbnail_path": thumbnail_output_path,
            }

        except Exception as e:
            logger.exception(f"Document processing failed for {original_filename}: {str(e)}")
            return {"success": False, "error": f"Failed to process document: {str(e)}"}

    @staticmethod
    def extract_pages(source_pdf: str, dest_pdf: str, pages_1_based: list) -> int:
        """Write a new PDF containing only the given pages (in ascending order). Returns the page count."""
        doc = fitz.open(source_pdf)
        try:
            doc.select([p - 1 for p in pages_1_based])
            os.makedirs(os.path.dirname(dest_pdf), exist_ok=True)
            doc.save(dest_pdf)
            return len(doc)
        finally:
            doc.close()

    @staticmethod
    def _convert_image_to_pdf(image_path: str, pdf_output_path: str):
        """Converts JPG/PNG image to standard printable A4 PDF using Pillow."""
        img = Image.open(image_path)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        
        # Save directly as PDF
        img.save(pdf_output_path, "PDF", resolution=300.0)

    @staticmethod
    def _convert_word_to_pdf(word_path: str, output_dir: str) -> Tuple[bool, Optional[str]]:
        """Converts DOC/DOCX to PDF using LibreOffice headless command line."""
        soffice_cmd = shutil.which("soffice") or shutil.which("libreoffice")
        
        if soffice_cmd:
            cmd = [
                soffice_cmd,
                "--headless",
                "--convert-to", "pdf",
                "--outdir", output_dir,
                word_path
            ]
            try:
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
                if res.returncode == 0:
                    converted_pdf = os.path.join(output_dir, os.path.splitext(os.path.basename(word_path))[0] + ".pdf")
                    target_pdf = os.path.join(output_dir, "printable.pdf")
                    if os.path.exists(converted_pdf):
                        if converted_pdf != target_pdf:
                            os.replace(converted_pdf, target_pdf)
                        return True, None
                logger.error(f"LibreOffice conversion failed: {res.stderr.decode('utf-8', errors='ignore')}")
            except Exception as e:
                logger.error(f"LibreOffice command execution error: {str(e)}")

        # Python-docx fallback if LibreOffice is missing or failed on basic text DOCX
        try:
            from docx import Document
            doc = Document(word_path)
            full_text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
            
            # Use PyMuPDF to generate a clean PDF from text
            pdf_doc = fitz.open()
            page = pdf_doc.new_page()
            rect = fitz.Rect(50, 50, 550, 790)
            page.insert_textbox(rect, full_text or "Word Document Content", fontsize=12)
            pdf_doc.save(os.path.join(output_dir, "printable.pdf"))
            pdf_doc.close()
            return True, None
        except Exception as fallback_err:
            logger.error(f"Fallback docx conversion failed: {str(fallback_err)}")
            return False, "LibreOffice conversion unavailable. Please convert Word file to PDF and send."

    @staticmethod
    def _get_pdf_page_count_and_thumbnail(pdf_path: str, thumbnail_path: str) -> int:
        """Parses PDF using PyMuPDF fitz, returns page count and renders first page thumbnail."""
        doc = fitz.open(pdf_path)
        page_count = len(doc)
        
        if page_count > 0:
            # Render page 1 as thumbnail image for admin dashboard preview
            page = doc[0]
            pix = page.get_pixmap(dpi=120)
            os.makedirs(os.path.dirname(thumbnail_path), exist_ok=True)
            pix.save(thumbnail_path)
            
        doc.close()
        return page_count

document_service = DocumentService()
