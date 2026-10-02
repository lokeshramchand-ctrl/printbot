from app.database import MongoSession
from app.models.printer import Printer
from app.models.print_job import PrintJob
from app.services.print_service import print_service
from tests.test_serial_numbering import _make_order, _make_pdf


def _printer(db, name, online=True, color=True):
    p = Printer(name=name, cups_name=name, is_online=online, is_color_supported=color,
                status="ONLINE" if online else "OFFLINE")
    db.add(p)
    db.commit()
    return p


def _clean(db):
    for coll in ("printers", "print_jobs"):
        db.database[coll].delete_many({})


def test_job_goes_to_the_only_online_printer(setup_db, tmp_path):
    db = MongoSession()
    _clean(db)
    _printer(db, "off1", online=False)
    on = _printer(db, "on1")
    order = _make_order(db, "PRN-Q-1", _make_pdf(tmp_path))
    job = print_service.submit_job(db, order)
    assert job.printer_id == on.id


def test_queue_piles_up_when_all_off_and_prints_when_turned_on(setup_db, tmp_path):
    db = MongoSession()
    _clean(db)
    p1 = _printer(db, "a", online=False)
    _printer(db, "b", online=False)
    orders = [_make_order(db, f"PRN-Q-{i}", _make_pdf(tmp_path, f"d{i}.pdf")) for i in (2, 3)]
    jobs = [print_service.submit_job(db, o) for o in orders]
    for j in jobs:
        assert j.printer_id is None and j.status == "QUEUED"
        assert print_service.execute_print_job(db, j.id) is False
    assert all(o.current_state == "QUEUED" for o in orders)

    p1.is_online = True
    db.commit()
    printed = print_service.dispatch_queue(db)
    assert printed == ["PRN-Q-2", "PRN-Q-3"]
    for o in orders:
        db.refresh(o)
        assert o.current_state == "COMPLETED"
    assert db.query(PrintJob).filter(PrintJob.status == "QUEUED").count() == 0


def test_both_on_spreads_load(setup_db, tmp_path):
    db = MongoSession()
    _clean(db)
    a, b = _printer(db, "x"), _printer(db, "y")
    used = set()
    for i in (4, 5):
        o = _make_order(db, f"PRN-Q-{i}", _make_pdf(tmp_path, f"s{i}.pdf"))
        j = print_service.submit_job(db, o)
        print_service.execute_print_job(db, j.id)
        used.add(j.printer_id)
    assert used == {a.id, b.id}
