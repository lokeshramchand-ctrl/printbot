from datetime import datetime
from typing import Any, Iterable

from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument
from sqlalchemy import func
from sqlalchemy.inspection import inspect as sqlalchemy_inspect
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql.elements import BooleanClauseList, BinaryExpression, UnaryExpression

from app.config import settings

Base = declarative_base()


def _model_collection(model: type) -> str:
    return model.__tablename__


def _column_name(column: Any) -> str:
    return column.key


def _relationship_value(instance: Any, model: type, column: Any) -> Any:
    if getattr(column, "class_", model) is model:
        return getattr(instance, _column_name(column), None)

    mapper = sqlalchemy_inspect(model)
    for relation in mapper.relationships:
        if relation.mapper.class_ is getattr(column, "class_", None):
            related = getattr(instance, relation.key, None)
            if related is None:
                return None
            return getattr(related, _column_name(column), None)
    return None


def _evaluate(expression: Any, instance: Any, model: type) -> bool:
    if isinstance(expression, BooleanClauseList):
        values = [_evaluate(clause, instance, model) for clause in expression.clauses]
        return all(values) if expression.operator.__name__ == "and_" else any(values)

    if isinstance(expression, BinaryExpression):
        left = expression.left
        right = expression.right
        left_value = _value(left, instance, model)
        right_value = _value(right, instance, model)
        operator_name = expression.operator.__name__
        if operator_name in ("eq", "is_", "is_not"):
            return left_value == right_value
        if operator_name in ("ne", "is_distinct_from"):
            return left_value != right_value
        if operator_name in ("ge", "gt", "le", "lt"):
            if left_value is None:
                return False
            return {"ge": left_value >= right_value, "gt": left_value > right_value,
                    "le": left_value <= right_value, "lt": left_value < right_value}[operator_name]
        if operator_name == "in_op":
            return left_value in right_value
        if operator_name == "not_in_op":
            return left_value not in right_value
        if operator_name == "ilike_op":
            return str(right_value).strip("%").lower() in str(left_value or "").lower()
        if operator_name == "not_ilike_op":
            return str(right_value).strip("%").lower() not in str(left_value or "").lower()
        return False

    if isinstance(expression, UnaryExpression):
        return not _evaluate(expression.element, instance, model)

    return bool(_value(expression, instance, model))


def _value(value: Any, instance: Any, model: type) -> Any:
    if hasattr(value, "key") and hasattr(value, "table"):
        return _relationship_value(instance, model, value)
    if hasattr(value, "value"):
        return value.value
    return value


def _numeric_value(expression: Any, instance: Any, model: type) -> float:
    if hasattr(expression, "left") and hasattr(expression, "right"):
        left = _numeric_value(expression.left, instance, model)
        right = _numeric_value(expression.right, instance, model)
        operator_name = expression.operator.__name__
        if operator_name == "mul":
            return left * right
        if operator_name == "add":
            return left + right
        if operator_name == "sub":
            return left - right
    value = _value(expression, instance, model)
    return float(value or 0)


def _mapped_model(expression: Any) -> type | None:
    mapper = getattr(expression, "_annotations", {}).get("parententity")
    if mapper is not None:
        return mapper.class_
    for attribute in ("left", "right"):
        child = getattr(expression, attribute, None)
        if child is not None:
            model = _mapped_model(child)
            if model is not None:
                return model
    return None


class MongoQuery:
    def __init__(self, session: "MongoSession", entities: tuple[Any, ...]):
        self.session = session
        self.entities = entities
        self.filters: list[Any] = []
        self.offset_value = 0
        self.limit_value: int | None = None
        self.ordering: list[tuple[Any, int]] = []

    @property
    def model(self) -> type:
        entity = self.entities[0]
        return entity if isinstance(entity, type) else _mapped_model(list(entity.clauses)[0])

    def filter(self, *expressions: Any) -> "MongoQuery":
        self.filters.extend(expressions)
        return self

    def join(self, *_args: Any, **_kwargs: Any) -> "MongoQuery":
        return self

    def order_by(self, *expressions: Any) -> "MongoQuery":
        for expression in expressions:
            modifier = getattr(expression, "modifier", None)
            direction = DESCENDING if getattr(modifier, "__name__", "") == "desc_op" else ASCENDING
            self.ordering.append((getattr(expression, "element", expression), direction))
        return self

    def offset(self, value: int) -> "MongoQuery":
        self.offset_value = value
        return self

    def limit(self, value: int) -> "MongoQuery":
        self.limit_value = value
        return self

    def _items(self) -> list[Any]:
        model = self.model
        items = [self.session._materialize(model, doc) for doc in self.session.database[_model_collection(model)].find({})]
        for expression in self.filters:
            items = [item for item in items if _evaluate(expression, item, model)]
        for expression, direction in reversed(self.ordering):
            items.sort(key=lambda item: (_value(expression, item, model) is None, _value(expression, item, model)), reverse=direction == DESCENDING)
        if self.offset_value:
            items = items[self.offset_value:]
        if self.limit_value is not None:
            items = items[:self.limit_value]
        return items

    def all(self) -> list[Any]:
        if self._is_aggregate():
            return [self.scalar()]
        return self._items()

    def first(self) -> Any:
        items = self.limit(1)._items()
        return items[0] if items else None

    def count(self) -> int:
        return len(self._items())

    def scalar(self) -> Any:
        expression = self.entities[0]
        items = self._items_for_aggregate()
        if expression.name == "count":
            return len(items)
        if expression.name == "sum":
            operand = list(expression.clauses)[0]
            return sum(_numeric_value(operand, item, self.model) for item in items)
        return None

    def _is_aggregate(self) -> bool:
        return not isinstance(self.entities[0], type) and getattr(self.entities[0], "name", None) in ("count", "sum")

    def _items_for_aggregate(self) -> list[Any]:
        expression = self.entities[0]
        clauses = getattr(expression, "clauses", None)
        operand = list(clauses)[0] if clauses is not None else None
        model = _mapped_model(operand)
        if model is not None:
            self.entities = (model,)
        return self._items()


class MongoSession:
    def __init__(self):
        self.client = MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=5000)
        self.database = self.client[settings.MONGODB_DATABASE]
        self._pending: list[Any] = []
        self._tracked: dict[tuple[type, Any], Any] = {}

    def query(self, *entities: Any) -> MongoQuery:
        return MongoQuery(self, entities)

    def add(self, instance: Any) -> None:
        self._pending.append(instance)
        self._track(instance)

    def _track(self, instance: Any) -> None:
        mapper = sqlalchemy_inspect(instance.__class__)
        primary_key = getattr(instance, mapper.primary_key[0].key, None)
        self._tracked[(instance.__class__, primary_key)] = instance

    def commit(self) -> None:
        for instance in self._pending:
            self._save(instance)
        self._pending.clear()
        for instance in self._tracked.values():
            self._save(instance)

    def rollback(self) -> None:
        self._pending.clear()

    def refresh(self, instance: Any) -> None:
        mapper = sqlalchemy_inspect(instance.__class__)
        key_name = mapper.primary_key[0].key
        key_value = getattr(instance, key_name)
        document = self.database[_model_collection(instance.__class__)].find_one({key_name: key_value})
        if document:
            for column in mapper.columns:
                if column.key in document:
                    setattr(instance, column.key, document[column.key])
        self._track(instance)

    def close(self) -> None:
        self.client.close()

    def _save(self, instance: Any) -> None:
        model = instance.__class__
        mapper = sqlalchemy_inspect(model)
        key_column = mapper.primary_key[0]
        key_value = getattr(instance, key_column.key, None)
        if key_value is None:
            key_value = self.database[_model_collection(model)].count_documents({}) + 1
            setattr(instance, key_column.key, key_value)
        document = {}
        for column in mapper.columns:
            value = getattr(instance, column.key, None)
            if value is None and column.default is not None:
                default = column.default.arg
                if callable(default):
                    try:
                        value = default()
                    except TypeError:
                        value = default(None)
                else:
                    value = default
                setattr(instance, column.key, value)
            document[column.key] = value
        self.database[_model_collection(model)].replace_one({key_column.key: key_value}, document, upsert=True)
        self._track(instance)

    def _materialize(self, model: type, document: dict[str, Any], hydrate_relationships: bool = True) -> Any:
        values = {column.key: document.get(column.key) for column in sqlalchemy_inspect(model).columns}
        instance = model(**values)
        self._track(instance)
        if hydrate_relationships:
            self._hydrate_relationships(instance)
        return instance

    def _hydrate_relationships(self, instance: Any) -> None:
        model = instance.__class__
        primary_key = sqlalchemy_inspect(model).primary_key[0].key
        primary_value = getattr(instance, primary_key, None)
        relations = {
            "Order": {
                "customer": ("customers", "id", "customer_id", False),
                "printer": ("printers", "id", "printer_id", False),
                "payments": ("payments", "order_id", "id", True),
                "print_jobs": ("print_jobs", "order_id", "id", True),
                "history": ("order_status_history", "order_id", "id", True),
                "uploaded_files": ("uploaded_files", "order_id", "id", True),
            },
            "Customer": {
                "orders": ("orders", "customer_id", "id", True),
                "messages": ("whatsapp_messages", "customer_id", "id", True),
            },
            "Printer": {
                "orders": ("orders", "printer_id", "id", True),
                "print_jobs": ("print_jobs", "printer_id", "id", True),
            },
            "Payment": {"order": ("orders", "id", "order_id", False)},
            "PrintJob": {
                "order": ("orders", "id", "order_id", False),
                "printer": ("printers", "id", "printer_id", False),
            },
            "OrderStatusHistory": {"order": ("orders", "id", "order_id", False)},
            "UploadedFile": {"order": ("orders", "id", "order_id", False)},
            "WhatsAppMessage": {"customer": ("customers", "id", "customer_id", False)},
        }.get(model.__name__, {})
        for relation_name, (collection, target_key, source_key, many) in relations.items():
            source_value = primary_value if source_key == primary_key else getattr(instance, source_key, None)
            if source_value is None:
                setattr(instance, relation_name, [] if many else None)
                continue
            query = {target_key: source_value}
            documents = list(self.database[collection].find(query))
            if many:
                setattr(instance, relation_name, [
                    self._materialize_from_collection(collection, document)
                    for document in documents
                ])
            else:
                setattr(instance, relation_name, (
                    self._materialize_from_collection(collection, documents[0]) if documents else None
                ))

    def _materialize_from_collection(self, collection: str, document: dict[str, Any]) -> Any:
        from app.models import MODEL_BY_TABLE
        model = MODEL_BY_TABLE[collection]
        return self._materialize(model, document, hydrate_relationships=False)


def initialize_mongodb() -> None:
    client = MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=5000)
    database = client[settings.MONGODB_DATABASE]
    database.admins.create_index("username", unique=True)
    database.admins.create_index("email", unique=True)
    database.customers.create_index("whatsapp_number")
    database.customers.create_index("telegram_chat_id")
    database.orders.create_index("print_serial", unique=True, sparse=True)
    database.orders.create_index([("created_at", DESCENDING)])
    database.orders.create_index([("current_state", ASCENDING), ("created_at", DESCENDING)])
    database.printers.create_index("cups_name", unique=True)
    database.webhook_events.create_index("event_id", unique=True)
    database.serial_counters.create_index("date_key", unique=True)
    database.print_jobs.create_index([("status", ASCENDING), ("queue_sequence", ASCENDING)])
    client.close()


SessionLocal = MongoSession


def get_db():
    db = MongoSession()
    try:
        yield db
    finally:
        db.close()
