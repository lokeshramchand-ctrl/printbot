"""Shared test setup: run everything against an in-memory MongoDB (mongomock).

The app only ever talks to MongoDB, so tests use the same MongoSession shim
and the same code paths as production -- just with a ``mongomock://`` URI so
no network or second database engine is involved.
"""
import os

os.environ["MONGODB_URI"] = "mongomock://tests"
os.environ["MONGODB_DATABASE"] = "printbot_test"
os.environ["PAYMENT_MODE"] = "demo"
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["USE_VIRTUAL_PRINTER"] = "true"

import pytest

from app import database
from app.database import MongoSession
from app.services.pricing_service import pricing_service


@pytest.fixture(autouse=True)
def setup_db():
    database.reset_client()
    db = MongoSession()
    db.client.drop_database("printbot_test")
    pricing_service.seed_defaults_if_empty(db)
    yield db
    db.client.drop_database("printbot_test")
    db.close()
    database.reset_client()
