"""Smoke tests against the *running* backend container (docker compose sets BACKEND_URL)."""
import os

import httpx
import pytest

from app.config import settings

URL = os.environ.get("BACKEND_URL")
pytestmark = pytest.mark.skipif(not URL, reason="BACKEND_URL not set (not running under docker compose)")


@pytest.fixture(scope="module")
def http():
    with httpx.Client(base_url=URL, timeout=15) as c:
        yield c


def test_health_reports_database_up(http):
    body = http.get("/health").json()
    assert body["status"] == "ok" and body["database"] == "up"


def test_admin_login_and_seeded_pricing(http):
    assert http.get("/api/orders").status_code == 401
    res = http.post("/api/auth/login", json={"username": settings.ADMIN_DEFAULT_USERNAME,
                                              "password": settings.ADMIN_DEFAULT_PASSWORD})
    assert res.status_code == 200, res.text
    headers = {"Authorization": f"Bearer {res.json()['access_token']}"}
    assert http.get("/api/orders", headers=headers).status_code == 200
    rules = http.get("/api/pricing", headers=headers)
    assert rules.status_code == 200 and len(rules.json()) > 0
