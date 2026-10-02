import os
import fitz
import pytest
from PIL import Image
from app.database import MongoSession
from app.services.document_service import document_service
from app.services.pricing_service import pricing_service
from app.services.razorpay_service import razorpay_service
from app.services.print_service import print_service
from app.models.pricing import PricingRule
from app.models.customer import Customer
from app.models.order import Order


def test_document_processing_image_to_pdf(tmp_path):
    """Test image creation and PDF conversion."""
    img_path = str(tmp_path / "sample.jpg")
    img = Image.new("RGB", (800, 600), color="blue")
    img.save(img_path)

    res = document_service.process_file(img_path, "PRN-TEST1", "sample.jpg")
    assert res["success"] is True
    assert res["page_count"] == 1
    assert os.path.exists(res["pdf_path"])

def test_document_processing_unsupported_file():
    """Test rejection of unsupported file types."""
    assert document_service.is_supported("archive.zip") is False
    assert document_service.is_supported("script.exe") is False
    assert document_service.is_supported("document.pdf") is True
    assert document_service.is_supported("photo.png") is True
    assert document_service.is_supported("assignment.docx") is True

def test_pricing_calculation(setup_db):
    """Test price engine for various configurations."""
    db = setup_db
    # A4 B&W Single (₹2/pg * 10 pgs * 1 copy = ₹20)
    p1 = pricing_service.calculate_price(db, "A4", "BW", "single", total_pages=10, copies=1)
    assert p1["total_amount"] == 20.0
    assert p1["rate_per_page"] == 2.0

    # A4 Color Single (₹10/pg * 5 pgs * 2 copies = ₹100)
    p2 = pricing_service.calculate_price(db, "A4", "Color", "single", total_pages=5, copies=2)
    assert p2["total_amount"] == 100.0

    # Minimum order price enforcement (1 pg A4 BW = ₹2 -> enforces min ₹5)
    p3 = pricing_service.calculate_price(db, "A4", "BW", "single", total_pages=1, copies=1)
    assert p3["total_amount"] == 5.0

async def test_razorpay_payment_link_generation():
    """Placeholder credentials must not produce a fake checkout URL."""
    res = await razorpay_service.create_payment_link(
        order_id="PRN-9999",
        amount_inr=32.0,
        customer_phone="+919876543210",
        description="Test Order"
    )
    assert res["success"] is False
    assert "payment_url" not in res

def test_print_queue_execution(setup_db, tmp_path):
    """Test print queue job creation and virtual execution."""
    db = setup_db
    customer = Customer(whatsapp_number="+919876543210", display_name="Test User")
    db.add(customer)
    db.commit()

    # Create dummy pdf
    pdf_path = str(tmp_path / "test.pdf")
    doc = fitz.open()
    doc.new_page()
    doc.save(pdf_path)
    doc.close()

    order = Order(
        id="PRN-1001",
        customer_id=customer.id,
        original_file_name="test.pdf",
        printable_pdf_path=pdf_path,
        total_pages=1,
        copies=1,
        paper_size="A4",
        color_mode="BW",
        sides="single",
        total_amount=5.0,
        payment_status="PAID",
        current_state="PAID"
    )
    db.add(order)
    db.commit()

    # Submit job
    job = print_service.submit_job(db, order)
    assert job.status == "QUEUED"
    assert order.current_state == "QUEUED"

    # Execute job
    success = print_service.execute_print_job(db, job.id)
    assert success is True
    assert order.current_state == "COMPLETED"
