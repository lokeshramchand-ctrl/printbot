from app.database import MongoSession
from app.models.customer import Customer
from app.models.order import Order


def test_ids_never_collide_after_delete(setup_db):
    db = setup_db
    for n in range(3):
        db.add(Customer(whatsapp_number=f"n{n}", display_name="x"))
    db.commit()
    db.database.customers.delete_one({"id": 1})
    db.add(Customer(whatsapp_number="late", display_name="x"))
    db.commit()
    ids = sorted(d["id"] for d in db.database.customers.find({}))
    assert ids == [2, 3, 4]


def test_commit_writes_only_changed_fields(setup_db):
    """A stale in-memory copy must not clobber fields another session changed."""
    a, b = MongoSession(), MongoSession()
    a.add(Customer(whatsapp_number="1", display_name="Old"))
    a.commit()
    stale = a.query(Customer).filter(Customer.whatsapp_number == "1").first()
    fresh = b.query(Customer).filter(Customer.whatsapp_number == "1").first()
    fresh.display_name = "New name"
    b.commit()
    stale.bot_state = "ASK_COPIES"
    a.commit()
    stored = a.database.customers.find_one({"whatsapp_number": "1"})
    assert stored["display_name"] == "New name"
    assert stored["bot_state"] == "ASK_COPIES"


def test_identity_map_returns_same_object(setup_db):
    db = setup_db
    db.add(Customer(whatsapp_number="9", display_name="x"))
    db.commit()
    one = db.query(Customer).filter(Customer.whatsapp_number == "9").first()
    two = db.query(Customer).filter(Customer.whatsapp_number == "9").first()
    assert one is two


def test_equality_filters_are_pushed_down_and_rechecked(setup_db):
    db = setup_db
    db.add(Customer(whatsapp_number="a", telegram_chat_id="1", display_name="x"))
    db.add(Customer(whatsapp_number="b", telegram_chat_id="2", display_name="y"))
    db.commit()
    assert db.query(Customer).filter(Customer.telegram_chat_id == "2").first().whatsapp_number == "b"
    assert db.query(Customer).filter(Customer.telegram_chat_id.in_(["1", "2"])).count() == 2
    assert db.query(Customer).filter(Customer.telegram_chat_id == "zzz").first() is None
