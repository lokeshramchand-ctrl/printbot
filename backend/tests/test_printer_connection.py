"""Printers registered from the mobile app's Wi-Fi / Bluetooth discovery."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.print_service import PrintService
from test_api import auth


@pytest.fixture
def client(setup_db):
    with TestClient(app) as c:
        yield c


def _payload(**over):
    body = {"name": "Front Desk", "cups_name": "Front_Desk_1_40", "model": "Canon MF445dw", "location": "Counter",
            "supported_paper_sizes": "A4,Letter", "is_color_supported": False,
            "connection_type": "WIFI", "connection_uri": "ipp://192.168.1.40:631/ipp/print"}
    body.update(over)
    return body


def test_wifi_printer_is_created_through_cups(client, monkeypatch):
    calls = []
    monkeypatch.setattr(PrintService, "register_network_printer",
                        classmethod(lambda cls, name, uri: calls.append((name, uri)) or None))
    res = client.post("/api/printers", json=_payload(), headers=auth(client))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["connection_type"] == "WIFI"
    assert body["connection_uri"] == "ipp://192.168.1.40:631/ipp/print"
    assert calls == [("Front_Desk_1_40", "ipp://192.168.1.40:631/ipp/print")]


def test_cups_failure_is_reported_and_nothing_saved(client, monkeypatch):
    monkeypatch.setattr(PrintService, "register_network_printer",
                        classmethod(lambda cls, name, uri: "lpadmin failed"))
    headers = auth(client)
    res = client.post("/api/printers", json=_payload(), headers=headers)
    assert res.status_code == 502
    assert "lpadmin failed" in res.json()["detail"]
    names = [p["cups_name"] for p in client.get("/api/printers", headers=headers).json()]
    assert "Front_Desk_1_40" not in names


def test_wifi_printer_needs_a_network_uri(client):
    res = client.post("/api/printers", json=_payload(connection_uri="bluetooth://AA:BB"), headers=auth(client))
    assert res.status_code == 400


def test_bluetooth_printer_is_saved_without_touching_cups(client, monkeypatch):
    monkeypatch.setattr(PrintService, "register_network_printer",
                        classmethod(lambda cls, name, uri: pytest.fail("CUPS must not be called for Bluetooth")))
    res = client.post("/api/printers", headers=auth(client),
                      json=_payload(cups_name="mpt2", connection_type="BLUETOOTH", connection_uri="bluetooth://AA:BB:CC"))
    assert res.status_code == 200, res.text
    assert res.json()["connection_type"] == "BLUETOOTH"


def test_unknown_connection_type_rejected(client):
    assert client.post("/api/printers", json=_payload(connection_type="FAX"), headers=auth(client)).status_code == 422


def test_existing_printers_default_to_cups(client):
    printers = client.get("/api/printers", headers=auth(client)).json()
    assert printers and printers[0]["connection_type"] in ("CUPS", None)
