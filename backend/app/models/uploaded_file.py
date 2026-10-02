from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, BigInteger
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(String(30), ForeignKey("orders.id"), nullable=False, index=True)
    original_name = Column(String(255), nullable=False)
    stored_name = Column(String(255), nullable=False)
    stored_path = Column(String(500), nullable=False)
    pdf_path = Column(String(500), nullable=True)
    file_type = Column(String(20), nullable=False)
    file_size_bytes = Column(BigInteger, default=0)
    page_count = Column(Integer, default=1)
    thumbnail_path = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    order = relationship("Order", back_populates="uploaded_files")
