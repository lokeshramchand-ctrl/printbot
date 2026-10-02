"""Database schema: validators, unique/partial indexes, TTL. Real-Mongo checks skip on mongomock."""
from datetime import datetime

import pytest
from pymongo.errors import DuplicateKeyError, WriteError

from app.config import settings
from app.db_schema import INDEXES, build_validator, ensure_schema
from app.models import MODEL_BY_TABLE

REAL = not settings.MONGODB_URI.startswith("mongomock://")
real_only = pytest.mark.skipif(not REAL, reason="needs a real MongoDB (validators/partial indexes)")

NOW = datetime.utcnow()


def order_doc(**over):
    doc = {"id": "PRN-T1", "customer_id": 1, "channel": "TELEGRAM", "total_pages": 1, "copies": 1,
           "payment_status": "PENDING", "current_state": "PAYMENT_PENDING", "print_status": "NOT_QUEUED",
           "sides": "single", "total_amount": 10.0, "print_serial": None, "created_at": NOW}
    doc.update(over)
    return doc


def test_validator_is_derived_for_every_model():
    for name, model in MODEL_BY_TABLE.items():
        schema = build_validator(model)["$jsonSchema"]
        assert "id" in schema["required"], name
        assert set(schema["properties"]) == {c.key for c in model.__table__.columns}, name
    orders = build_validator(MODEL_BY_TABLE["orders"])["$jsonSchema"]["properties"]
    assert orders["total_amount"]["minimum"] == 0 and "PAID" in orders["payment_status"]["enum"]
    assert orders["id"]["maxLength"] == 30


def test_ensure_schema_is_idempotent(setup_db):
    ensure_schema()
    ensure_schema()
    names = {ix["name"] for ix in setup_db.database.orders.list_indexes()}
    assert {"uq_order_print_serial", "ix_order_state_created"} <= names


def test_every_declared_index_exists(setup_db):
    for collection, _keys, options in INDEXES:
        names = {ix["name"] for ix in setup_db.database[collection].list_indexes()}
        assert options["name"] in names, (collection, options["name"])


@real_only
def test_validator_rejects_bad_documents(setup_db):
    orders = setup_db.database.orders
    for bad in (order_doc(total_amount=-1), order_doc(copies=0), order_doc(current_state="NONSENSE"),
                order_doc(payment_status="MAYBE"), order_doc(total_amount="ten"), order_doc(id="x" * 31)):
        with pytest.raises(WriteError):
            orders.insert_one(bad)
    orders.insert_one(order_doc())


@real_only
def test_unique_serial_ignores_nulls_but_rejects_duplicates(setup_db):
    orders = setup_db.database.orders
    orders.insert_one(order_doc(id="PRN-A"))
    orders.insert_one(order_doc(id="PRN-B"))  # two explicit nulls must coexist
    orders.insert_one(order_doc(id="PRN-C", print_serial="PB-20260101-000001"))
    with pytest.raises(DuplicateKeyError):
        orders.insert_one(order_doc(id="PRN-D", print_serial="PB-20260101-000001"))


@real_only
def test_one_customer_per_channel_identity(setup_db):
    customers = setup_db.database.customers
    base = {"channel": "TELEGRAM", "bot_state": "IDLE", "state_data": {}, "created_at": NOW}
    customers.insert_one({"id": 1, "telegram_chat_id": "42", "whatsapp_number": None, **base})
    customers.insert_one({"id": 2, "telegram_chat_id": "43", "whatsapp_number": None, **base})
    with pytest.raises(DuplicateKeyError):
        customers.insert_one({"id": 3, "telegram_chat_id": "42", "whatsapp_number": None, **base})
    with pytest.raises(WriteError):
        customers.insert_one({"id": 4, "telegram_chat_id": "44", "channel": "TELEGRAM", "bot_state": "HACKED"})


@real_only
def test_webhook_events_expire_via_ttl(setup_db):
    ttl = [ix for ix in setup_db.database.webhook_events.list_indexes() if "expireAfterSeconds" in ix]
    assert ttl and ttl[0]["expireAfterSeconds"] == 90 * 86400


@real_only
def test_legacy_sparse_index_is_replaced(setup_db):
    orders = setup_db.database.orders
    orders.drop_index("uq_order_print_serial")
    orders.create_index("print_serial", unique=True, sparse=True, name="print_serial_1")
    ensure_schema()
    names = {ix["name"] for ix in orders.list_indexes()}
    assert "print_serial_1" not in names and "uq_order_print_serial" in names
