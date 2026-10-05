"""MongoDB schema: collection validators, constraints and indexes.

Single source of truth is the SQLAlchemy models. Each collection's
``$jsonSchema`` validator is *derived* from the model columns (type, nullability,
max length), then tightened with the business rules in ``ENUMS``/``MINIMUMS``.
So a model change cannot silently drift from what the database enforces.

``ensure_schema`` is idempotent and safe on an existing database: validators use
``validationLevel=moderate`` (existing non-conforming documents are left alone,
all new writes and updates of conforming documents are checked).
"""
import logging
from typing import Any

from pymongo import ASCENDING, DESCENDING
from pymongo.errors import OperationFailure
from sqlalchemy import BigInteger, Boolean, DateTime, Float, Integer, JSON, String, Text

from app.config import settings
from app.database import get_client

logger = logging.getLogger("printbot.schema")

# Allowed values per (collection, field). Keep in sync with the services.
ENUMS: dict[str, dict[str, list[str]]] = {
    "admins": {"role": ["admin", "operator", "SUPERADMIN"]},
    "customers": {
        "channel": ["WHATSAPP", "TELEGRAM"],
        "bot_state": ["IDLE", "WAITING_FOR_FILE", "ASK_COPIES", "ASK_COLOR", "ASK_PAPER_SIZE", "ASK_PAGES",
                      "ASK_PAGE_RANGE", "ASK_SIDES", "WAITING_FOR_PAYMENT"],
    },
    "orders": {
        "channel": ["WHATSAPP", "TELEGRAM"],
        "payment_status": ["PENDING", "PAID", "FAILED", "REFUNDED"],
        "current_state": ["UPLOADED", "PAYMENT_PENDING", "PAID", "QUEUED", "PRINTING", "COMPLETED",
                          "PRINT_FAILED", "CANCELLED", "REFUNDED"],
        "print_status": ["NOT_QUEUED", "QUEUED", "PRINTING", "COMPLETED", "FAILED", "CANCELLED"],
        "sides": ["single", "double"],
    },
    "payments": {"status": ["CREATED", "CAPTURED", "FAILED", "REFUNDED", "EXPIRED", "CANCELLED"]},
    "printers": {"status": ["ONLINE", "BUSY", "OFFLINE", "ERROR"]},
    "print_jobs": {"status": ["QUEUED", "PRINTING", "COMPLETED", "FAILED", "CANCELLED"],
                   "sides": ["single", "double"]},
    "whatsapp_messages": {"direction": ["INBOUND", "OUTBOUND"]},
}

# Numeric lower bounds per (collection, field).
MINIMUMS: dict[str, dict[str, float]] = {
    "orders": {"total_pages": 0, "copies": 1, "rate_per_page": 0, "subtotal_amount": 0,
               "additional_charges": 0, "total_amount": 0, "file_size_bytes": 0},
    "payments": {"amount": 0},
    "pricing_rules": {"price_per_page": 0, "min_order_price": 0, "additional_charge": 0},
    "print_jobs": {"copies": 1, "total_pages": 0, "retry_count": 0},
    "printers": {"total_printed_jobs": 0},
    "serial_counters": {"last_value": 0},
}


def _bson_type(column: Any) -> Any:
    t = column.type
    if isinstance(t, Boolean):
        return "bool"
    if isinstance(t, (Integer, BigInteger)):
        return ["int", "long"]
    if isinstance(t, Float):
        return "number"
    if isinstance(t, DateTime):
        return "date"
    if isinstance(t, (String, Text)):
        return "string"
    if isinstance(t, JSON):
        return None  # any JSON value
    return None


def build_validator(model: type) -> dict[str, Any]:
    collection = model.__tablename__
    properties: dict[str, Any] = {}
    required: list[str] = []
    for column in model.__table__.columns:
        spec: dict[str, Any] = {}
        bson = _bson_type(column)
        if bson is not None:
            types = [bson] if isinstance(bson, str) else list(bson)
            if column.nullable and not column.primary_key:
                types.append("null")
            spec["bsonType"] = types if len(types) > 1 else types[0]
        length = getattr(column.type, "length", None)
        if isinstance(column.type, String) and length:
            spec["maxLength"] = length
        if column.key in ENUMS.get(collection, {}):
            spec["enum"] = ENUMS[collection][column.key] + ([None] if column.nullable else [])
        if column.key in MINIMUMS.get(collection, {}):
            spec["minimum"] = MINIMUMS[collection][column.key]
        properties[column.key] = spec
        if not column.nullable:
            required.append(column.key)
    return {"$jsonSchema": {"bsonType": "object", "required": sorted(required), "properties": properties}}


def _string_partial(field: str) -> dict[str, Any]:
    """Partial filter so unique indexes ignore documents where the field is null/absent
    (a sparse unique index still indexes explicit nulls and would reject a 2nd one)."""
    return {field: {"$type": "string"}}


# (collection, keys, options). Names are explicit so re-creation is deterministic.
INDEXES: list[tuple[str, list[tuple[str, int]], dict[str, Any]]] = [
    ("admins", [("username", ASCENDING)], {"unique": True, "name": "uq_admin_username"}),
    ("admins", [("email", ASCENDING)], {"unique": True, "name": "uq_admin_email"}),
    # One customer per channel identity; Telegram customers have no phone and vice versa.
    ("customers", [("whatsapp_number", ASCENDING)],
     {"unique": True, "name": "uq_customer_whatsapp", "partialFilterExpression": _string_partial("whatsapp_number")}),
    ("customers", [("telegram_chat_id", ASCENDING)],
     {"unique": True, "name": "uq_customer_telegram", "partialFilterExpression": _string_partial("telegram_chat_id")}),
    ("orders", [("print_serial", ASCENDING)],
     {"unique": True, "name": "uq_order_print_serial", "partialFilterExpression": _string_partial("print_serial")}),
    ("orders", [("created_at", DESCENDING)], {"name": "ix_order_created"}),
    ("orders", [("current_state", ASCENDING), ("created_at", DESCENDING)], {"name": "ix_order_state_created"}),
    ("orders", [("customer_id", ASCENDING), ("created_at", DESCENDING)], {"name": "ix_order_customer_created"}),
    ("orders", [("payment_status", ASCENDING), ("created_at", DESCENDING)], {"name": "ix_order_payment_created"}),
    ("printers", [("cups_name", ASCENDING)], {"unique": True, "name": "uq_printer_cups_name"}),
    ("print_jobs", [("status", ASCENDING), ("queue_sequence", ASCENDING)], {"name": "ix_job_status_queue"}),
    ("print_jobs", [("order_id", ASCENDING)], {"name": "ix_job_order"}),
    ("payments", [("order_id", ASCENDING), ("status", ASCENDING)], {"name": "ix_payment_order_status"}),
    ("payments", [("razorpay_payment_link_id", ASCENDING)],
     {"name": "ix_payment_link", "partialFilterExpression": _string_partial("razorpay_payment_link_id")}),
    # A given Razorpay payment can be recorded against only one Payment row.
    ("payments", [("razorpay_payment_id", ASCENDING)],
     {"unique": True, "name": "uq_payment_rzp_id", "partialFilterExpression": _string_partial("razorpay_payment_id")}),
    ("order_status_history", [("order_id", ASCENDING), ("created_at", ASCENDING)], {"name": "ix_history_order_time"}),
    ("whatsapp_messages", [("customer_id", ASCENDING), ("created_at", DESCENDING)], {"name": "ix_msg_customer_time"}),
    # Idempotency key for webhooks, plus automatic expiry of old events (90 days).
    ("webhook_events", [("event_id", ASCENDING)], {"unique": True, "name": "uq_webhook_event_id"}),
    ("webhook_events", [("created_at", ASCENDING)], {"name": "ttl_webhook_events", "expireAfterSeconds": 90 * 86400}),
    ("serial_counters", [("date_key", ASCENDING)], {"unique": True, "name": "uq_serial_date"}),
]

# Index names created by older versions that conflict with the definitions above.
LEGACY_INDEXES = {
    "orders": ["print_serial_1", "created_at_-1", "current_state_1_created_at_-1"],
    "admins": ["username_1", "email_1"],
    "customers": ["whatsapp_number_1", "telegram_chat_id_1"],
    "printers": ["cups_name_1"],
    "print_jobs": ["status_1_queue_sequence_1"],
    "payments": ["razorpay_payment_link_id_1", "razorpay_payment_id_1"],
    "webhook_events": ["event_id_1"],
    "serial_counters": ["date_key_1"],
}


def _create_index(database: Any, collection: str, keys: list, options: dict) -> None:
    try:
        database[collection].create_index(keys, **options)
    except OperationFailure as exc:
        # 85/86: same keys or name but different options -> replace with the canonical definition.
        if exc.code in (85, 86):
            logger.warning("Recreating index %s.%s with new options", collection, options["name"])
            for existing in database[collection].list_indexes():
                if existing["name"] == options["name"] or list(existing["key"].items()) == [(k, d) for k, d in keys]:
                    database[collection].drop_index(existing["name"])
            database[collection].create_index(keys, **options)
        else:
            raise


def ensure_schema(database: Any | None = None) -> None:
    """Create collections with validators and (re)apply indexes. Idempotent."""
    from app.models import MODEL_BY_TABLE

    database = database if database is not None else get_client()[settings.MONGODB_DATABASE]
    is_mock = settings.MONGODB_URI.startswith("mongomock://")
    existing = set(database.list_collection_names())

    for name, model in MODEL_BY_TABLE.items():
        if is_mock:
            break  # mongomock has no validator support
        validator = build_validator(model)
        if name in existing:
            database.command("collMod", name, validator=validator, validationLevel="moderate", validationAction="error")
        else:
            database.create_collection(name, validator=validator, validationLevel="moderate", validationAction="error")

    for collection, names in LEGACY_INDEXES.items():
        have = {ix["name"] for ix in database[collection].list_indexes()} if collection in existing else set()
        wanted = {opts["name"] for c, _, opts in INDEXES if c == collection}
        for legacy in names:
            if legacy in have and legacy not in wanted:
                database[collection].drop_index(legacy)

    for collection, keys, options in INDEXES:
        options = dict(options)
        if is_mock and "partialFilterExpression" in options:
            # mongomock ignores partial filters on unique indexes; sparse is the closest emulation.
            options.pop("partialFilterExpression")
            options["sparse"] = True
        _create_index(database, collection, keys, options)
