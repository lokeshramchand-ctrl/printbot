import httpx
import pytest

from printbot_agent.api import AgentApi, ApiError, ReportedPrinter, UnauthorizedError
from printbot_agent.config import Settings
from printbot_agent.runner import AgentRunner

JOB = {"id": 7, "order_id": "PRN-1", "serial": "PB-20260101-000001", "printer_system_name": "HP",
       "copies": 2, "paper_size": "A4", "color_mode": "COLOR", "sides": "double", "total_pages": 3,
       "file_url": "/api/agent/jobs/7/file"}


def make_api(handler):
    return AgentApi("http://srv", "tok", client=httpx.Client(transport=httpx.MockTransport(handler)))


def paired_settings(tmp_path):
    s = Settings(server_url="http://srv", token="tok", path=str(tmp_path / "c.json"))
    s.save()
    return s


def test_settings_roundtrip_and_clear(tmp_path):
    s = paired_settings(tmp_path)
    loaded = Settings.load(s.path)
    assert loaded.is_paired
    loaded.clear_pairing()
    assert not Settings.load(s.path).is_paired


def test_claim_parses_job_and_sends_bearer():
    seen = {}

    def handler(req):
        seen["auth"] = req.headers["authorization"]
        return httpx.Response(200, json={"job": JOB})

    job = make_api(handler).claim()
    assert seen["auth"] == "Bearer tok"
    assert (job.color, job.duplex, job.label, job.printer_name) == (True, True, "PB-20260101-000001", "HP")


def test_claim_none_and_401():
    assert make_api(lambda r: httpx.Response(200, json={"job": None})).claim() is None
    with pytest.raises(UnauthorizedError):
        make_api(lambda r: httpx.Response(401)).claim()


def test_api_error_detail():
    with pytest.raises(ApiError, match="Invalid or expired"):
        make_api(lambda r: httpx.Response(400, json={"detail": "Invalid or expired pairing code"})).pair(
            "X", "windows", "pc", "1")


def runner_for(tmp_path, handler, print_fn):
    s = paired_settings(tmp_path)
    r = AgentRunner(s, lambda c: [ReportedPrinter("HP")], print_fn,
                    api_factory=lambda: make_api(handler), report_retry_delay=0)
    r.running = True
    return r


def test_poll_prints_then_reports_completed(tmp_path):
    reports, claims, printed = [], iter([JOB, None]), []

    def handler(req):
        if req.url.path.endswith("/claim"):
            return httpx.Response(200, json={"job": next(claims)})
        if req.url.path.endswith("/file"):
            return httpx.Response(200, content=b"%PDF")
        reports.append(req.read())
        return httpx.Response(200, json={"status": "ok"})

    r = runner_for(tmp_path, handler, lambda job, pdf: printed.append((job.id, pdf)))
    r.poll()
    assert printed == [(7, b"%PDF")]
    assert b"COMPLETED" in reports[0]
    assert r.printed_count == 1 and r.current_job is None


def test_print_failure_reports_failed(tmp_path):
    reports, claims = [], iter([JOB, None])

    def handler(req):
        if req.url.path.endswith("/claim"):
            return httpx.Response(200, json={"job": next(claims)})
        if req.url.path.endswith("/file"):
            return httpx.Response(200, content=b"x")
        reports.append(req.read())
        return httpx.Response(200, json={})

    def boom(job, pdf):
        raise RuntimeError("paper jam")

    r = runner_for(tmp_path, handler, boom)
    r.poll()
    assert b"FAILED" in reports[0] and b"paper jam" in reports[0]
    assert r.printed_count == 0


def test_revoked_clears_pairing(tmp_path):
    r = runner_for(tmp_path, lambda req: httpx.Response(401), lambda j, p: None)
    r.beat()
    assert r.revoked and not r.running
    assert not Settings.load(r.settings.path).is_paired


def test_report_retries_through_network_blip(tmp_path):
    calls = {"n": 0}
    claims = iter([JOB, None])

    def handler(req):
        if req.url.path.endswith("/claim"):
            return httpx.Response(200, json={"job": next(claims)})
        if req.url.path.endswith("/file"):
            return httpx.Response(200, content=b"x")
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.ConnectError("down")
        return httpx.Response(200, json={})

    r = runner_for(tmp_path, handler, lambda j, p: None)
    r.poll()
    assert calls["n"] == 3 and r.printed_count == 1
