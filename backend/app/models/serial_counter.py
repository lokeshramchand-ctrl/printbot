from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from app.database import Base


class SerialCounter(Base):
    """
    A transaction-safe, date-scoped sequence used to generate the
    human-readable print serial (e.g. PB-20260906-000123).

    One row per calendar day (UTC). Incrementing is done with a single
    atomic ``UPDATE ... SET last_value = last_value + 1`` statement so
    concurrent requests (multiple workers, multiple admin actions, retries)
    can never observe or reuse the same value — the database's own
    write-serialization guarantees uniqueness, not application-level locking.
    See app/services/serial_service.py for the increment logic.
    """
    __tablename__ = "serial_counters"

    id = Column(Integer, primary_key=True, index=True)
    date_key = Column(String(8), unique=True, nullable=False, index=True)  # YYYYMMDD (UTC)
    last_value = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
