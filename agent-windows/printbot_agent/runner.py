"""Heartbeat + claim/print/report loops, running on background threads."""
import threading
import time
from collections import deque
from datetime import datetime
from typing import Callable, Deque, List, Optional

from . import __version__
from .api import AgentApi, AgentJob, ApiError, ReportedPrinter, UnauthorizedError
from .config import Settings

HEARTBEAT_EVERY = 15.0
POLL_EVERY = 5.0


class AgentRunner:
    def __init__(self, settings: Settings,
                 discover: Callable[[bool], List[ReportedPrinter]],
                 print_pdf: Callable[[AgentJob, bytes], None],
                 api_factory: Optional[Callable[[], AgentApi]] = None,
                 report_retry_delay: float = 2.0):
        self.settings = settings
        self._discover = discover
        self._print_pdf = print_pdf
        self._api_factory = api_factory or (lambda: AgentApi(settings.server_url, settings.token))
        self._retry_delay = report_retry_delay
        self.online = False
        self.revoked = False
        self.running = False
        self.last_heartbeat: Optional[datetime] = None
        self.current_job: Optional[str] = None
        self.printed_count = 0
        self.printers: List[ReportedPrinter] = []
        self.log: Deque[tuple] = deque(maxlen=100)  # (time, message, is_error), newest first
        self._stop = threading.Event()
        self._busy = threading.Lock()

    def _log(self, msg: str, error: bool = False) -> None:
        self.log.appendleft((datetime.now(), msg, error))

    def start(self) -> None:
        if self.running or not self.settings.is_paired:
            return
        self.running = True
        self.revoked = False
        self._stop.clear()
        self._log("Agent started")
        for fn, every in ((self.beat, HEARTBEAT_EVERY), (self.poll, POLL_EVERY)):
            threading.Thread(target=self._loop, args=(fn, every), daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        self.running = False
        self.online = False

    def _loop(self, fn: Callable[[], None], every: float) -> None:
        while not self._stop.is_set():
            try:
                fn()
            except Exception as e:  # a loop must never die silently
                self._log(f"Unexpected error: {e}", error=True)
            self._stop.wait(every)

    def refresh_printers(self) -> None:
        try:
            self.printers = self._discover(self.settings.system_printers_color)
        except Exception as e:
            self._log(f"Could not list printers: {e}", error=True)

    def beat(self) -> None:
        self.refresh_printers()
        try:
            self._api_factory().heartbeat(self.printers, __version__)
            self.last_heartbeat = datetime.now()
            if not self.online:
                self._log("Connected to server")
            self.online = True
        except UnauthorizedError:
            self._revoked()
        except ApiError as e:
            if self.online:
                self._log(f"Server unreachable: {e}", error=True)
            self.online = False

    def _revoked(self) -> None:
        if self.revoked:  # heartbeat and poll can both notice at once
            return
        self.revoked = True
        self.stop()
        self.settings.clear_pairing()
        self._log("This agent was removed in the dashboard. Pair again to continue.", error=True)

    def poll(self) -> None:
        """Claim and print jobs until the queue is empty. No-op if already busy."""
        if not self._busy.acquire(blocking=False):
            return
        try:
            while self.running and not self._stop.is_set():
                api = self._api_factory()
                try:
                    job = api.claim()
                    self.online = True
                except UnauthorizedError:
                    self._revoked()
                    return
                except ApiError as e:
                    if self.online:
                        self._log(f"Server unreachable: {e}", error=True)
                    self.online = False
                    return
                if job is None:
                    return
                self._handle(api, job)
        finally:
            self._busy.release()

    def _handle(self, api: AgentApi, job: AgentJob) -> None:
        self.current_job = f"{job.label} on {job.printer_name}"
        self._log(f"Printing {job.label} ({job.total_pages} pp x {job.copies}) on {job.printer_name}")
        success, error = False, None
        try:
            self._print_pdf(job, api.download(job))
            success = True
        except UnauthorizedError:
            self.current_job = None
            self._revoked()
            return
        except Exception as e:
            error = str(e)
        # Always tell the server the outcome, retrying through brief network blips.
        for attempt in range(5):
            try:
                api.report(job.id, success, error)
                break
            except UnauthorizedError:
                self.current_job = None
                self._revoked()
                return
            except ApiError:
                if attempt == 4:
                    self._log(f"Could not report result for {job.label}", error=True)
                else:
                    time.sleep(self._retry_delay)
        self.current_job = None
        if success:
            self.printed_count += 1
            self._log(f"Printed {job.label}")
        else:
            self._log(f"Failed {job.label}: {error}", error=True)
