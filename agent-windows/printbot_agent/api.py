"""Client for the PrintBot backend's /api/agent/* endpoints. No OS assumptions."""
from dataclasses import dataclass, field
from typing import List, Optional

import httpx


class UnauthorizedError(Exception):
    """401: the token was revoked (agent removed or re-paired in the dashboard)."""

    def __str__(self) -> str:
        return "This agent was removed or re-paired in the dashboard"


class ApiError(Exception):
    pass


@dataclass
class ReportedPrinter:
    name: str
    model: Optional[str] = None
    color: bool = True
    paper_sizes: List[str] = field(default_factory=lambda: ["A4"])
    state: Optional[str] = None  # "ok" | "error"

    def to_json(self) -> dict:
        return {"name": self.name, "model": self.model, "color": self.color,
                "paper_sizes": self.paper_sizes, "state": self.state}


@dataclass
class AgentJob:
    id: int
    order_id: str
    serial: Optional[str]
    printer_name: str
    copies: int
    paper_size: str
    color_mode: str
    sides: str
    total_pages: int
    file_url: str

    @classmethod
    def from_json(cls, j: dict) -> "AgentJob":
        return cls(
            id=int(j["id"]), order_id=j["order_id"], serial=j.get("serial"),
            printer_name=j["printer_system_name"], copies=int(j.get("copies") or 1),
            paper_size=j.get("paper_size") or "A4", color_mode=j.get("color_mode") or "BW",
            sides=j.get("sides") or "single", total_pages=int(j.get("total_pages") or 0),
            file_url=j["file_url"])

    @property
    def color(self) -> bool:
        return self.color_mode.upper() == "COLOR"

    @property
    def duplex(self) -> bool:
        return self.sides.lower() == "double"

    @property
    def label(self) -> str:
        return self.serial or self.order_id


class AgentApi:
    def __init__(self, base_url: str, token: Optional[str] = None, client: Optional[httpx.Client] = None):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._client = client or httpx.Client(timeout=20.0, follow_redirects=True)

    @property
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def _request(self, method: str, path: str, **kw) -> httpx.Response:
        try:
            r = self._client.request(method, f"{self.base_url}{path}", headers=self._headers, **kw)
        except httpx.HTTPError as e:
            raise ApiError(f"Cannot reach server: {e}") from e
        if r.status_code == 401:
            raise UnauthorizedError()
        return r

    @staticmethod
    def _fail(r: httpx.Response):
        detail = f"HTTP {r.status_code}"
        try:
            d = r.json()
            if isinstance(d, dict) and d.get("detail"):
                detail = str(d["detail"])
        except ValueError:
            pass
        raise ApiError(detail)

    def pair(self, code: str, platform: str, device_name: str, app_version: str) -> tuple:
        r = self._request("POST", "/api/agent/pair", json={
            "code": code, "platform": platform, "device_name": device_name, "app_version": app_version})
        if r.status_code != 200:
            self._fail(r)
        j = r.json()
        return j["token"], j["agent_name"]

    def heartbeat(self, printers: List[ReportedPrinter], app_version: str) -> None:
        r = self._request("POST", "/api/agent/heartbeat", json={
            "printers": [p.to_json() for p in printers], "app_version": app_version})
        if r.status_code != 200:
            self._fail(r)

    def claim(self) -> Optional[AgentJob]:
        r = self._request("POST", "/api/agent/jobs/claim")
        if r.status_code != 200:
            self._fail(r)
        job = r.json().get("job")
        return AgentJob.from_json(job) if job else None

    def download(self, job: AgentJob) -> bytes:
        r = self._request("GET", job.file_url)
        if r.status_code != 200:
            self._fail(r)
        return r.content

    def report(self, job_id: int, success: bool, error: Optional[str] = None) -> None:
        r = self._request("POST", f"/api/agent/jobs/{job_id}/report", json={
            "status": "COMPLETED" if success else "FAILED", "error": error})
        # 409 = already finalised (e.g. re-queued after a long silence); nothing more to do.
        if r.status_code not in (200, 409):
            self._fail(r)
