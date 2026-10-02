from sqlalchemy import Column, Integer, String, DateTime, Boolean
from datetime import datetime
from app.database import Base


class Agent(Base):
    """A print agent: the PC/phone app next to a physical printer.

    The shop admin creates an agent (gets a one-time pairing code); the app
    exchanges the code for a bearer token. Only SHA-256 hashes of the pairing
    code and the token are stored.
    """
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    platform = Column(String(30), nullable=True)       # windows, android, linux, macos, ...
    device_name = Column(String(100), nullable=True)
    app_version = Column(String(30), nullable=True)

    pairing_code_hash = Column(String(64), nullable=True)
    pairing_expires_at = Column(DateTime, nullable=True)
    token_hash = Column(String(64), nullable=True)
    paired_at = Column(DateTime, nullable=True)
    last_seen_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
