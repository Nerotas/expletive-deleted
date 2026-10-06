"""One background check, at most one queued replacement, and bounded timings."""

from __future__ import annotations

import copy
import json
import math
import subprocess
import sys
import time
from threading import Event, RLock, Thread
from uuid import uuid4
from typing import Callable, TYPE_CHECKING

from backend.runtime.check_progress import Progress, STAGES
from backend.settings.models import AppSettings
from backend.settings.serialization import settings_to_dict

if TYPE_CHECKING:
    from backend.service import BackendService

_BOOTSTRAP = "import json,sys; request=json.load(sys.stdin); sys.path[:]=request['sys_path']; from backend.runtime.system_check_worker import run; run(request['settings'])"


def run_check(settings: AppSettings, progress: Progress, cancellation: Event) -> dict[str, object]:
    process = subprocess.Popen(
        [sys.executable, "-B", "-c", _BOOTSTRAP],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, encoding="utf-8", errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    done = Event()
    completed = False

    def cancel():
        while not done.is_set():
            if cancellation.wait(0.1):
                try:
                    process.terminate()
                except OSError:
                    pass
                return

    Thread(target=cancel, daemon=True, name="system-check-cancellation").start()
    try:
        process.stdin.write(json.dumps({"settings": settings_to_dict(settings), "sys_path": sys.path}))
        process.stdin.close()
        while True:
            line = process.stdout.readline(131072)
            if not line:
                raise RuntimeError("Verification process stopped")
            if not line.endswith("\n"):
                raise RuntimeError("Verification response exceeded its limit")
            value = json.loads(line)
            if value.get("type") == "progress":
                stage, state, duration = value.get("stage"), value.get("state"), value.get("duration_ms")
                if stage not in STAGES or state not in {"started", "completed", "failed"} or not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration < 0:
                    raise RuntimeError("Invalid verification progress")
                progress(stage, state, duration)
            elif value.get("type") == "result" and isinstance(value.get("capabilities"), dict):
                completed = True
                return value["capabilities"]
            else:
                raise RuntimeError("Verification could not complete")
    finally:
        done.set()
        if process.poll() is None and (not completed or cancellation.is_set()):
            try:
                process.terminate()
            except OSError:
                pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        if not process.stdin.closed:
            process.stdin.close()
        process.stdout.close()


class SystemCheckController:
    def __init__(self, service: BackendService, *, probe: Callable[[AppSettings, Progress, Event], dict[str, object]] = run_check):
        self.service, self.probe = service, probe
        self._lock = RLock()
        self._cancellation = Event()
        self._active = False
        self._state = None
        self._settings = None
        self._queued = False

    def _new(self, settings: AppSettings, *, queued: bool = False) -> None:
        self._settings = settings
        self._queued = queued
        self._started = self._stage_started = time.monotonic()
        self._state = {"check_id": uuid4().hex, "status": "running",
                       "stage": "waiting_previous_check" if queued else "starting", "elapsed_ms": 0,
                       "stage_elapsed_ms": 0, "timings": {}, "capabilities": None, "error": None}

    def start(self, *, refresh: bool = False) -> dict[str, object]:
        with self._lock:
            if self._cancellation.is_set():
                raise RuntimeError("The local service is closing")
            settings = self.service.settings
            if self._state and not refresh and settings == self._settings:
                return self.status()
            if self._active:
                # Reconnect reuses the original check. A changed configuration or
                # approved setup queues one replacement, never a parallel probe.
                if settings != self._settings or (refresh and not self._queued):
                    self._new(settings, queued=True)
            else:
                self._new(settings)
                self._active = True
                Thread(target=self._run, daemon=True, name="system-verification").start()
            return self.status()

    def status(self) -> dict[str, object] | None:
        with self._lock:
            if self._state is None:
                return None
            if not self._active and self.service.settings != self._settings and not self._cancellation.is_set():
                return self.start()
            result = copy.deepcopy(self._state)
            if result["status"] == "running":
                result["elapsed_ms"] = (time.monotonic() - self._started) * 1000
                result["stage_elapsed_ms"] = (time.monotonic() - self._stage_started) * 1000
            return result

    def _run(self) -> None:
        while not self._cancellation.is_set():
            with self._lock:
                check_id, settings = self._state["check_id"], self._settings
                self._queued = False

            def progress(stage, state, duration_ms):
                with self._lock:
                    if self._state["check_id"] != check_id or self._cancellation.is_set():
                        return
                    if stage not in STAGES:
                        raise ValueError("Unknown verification stage")
                    if state == "started":
                        self._state["stage"] = stage
                        self._stage_started = time.monotonic()
                    else:
                        self._state["timings"][stage] = duration_ms

            try:
                capabilities = self.probe(settings, progress, self._cancellation)
                error = None
            except Exception:
                capabilities = None
                error = "Verification could not complete. Review the component timings, check components in Settings, and retry."
            with self._lock:
                if self._cancellation.is_set():
                    return
                if self.service.settings != self._settings:
                    self._new(self.service.settings, queued=True)
                if self._state["check_id"] != check_id:
                    continue
                self._state.update(status="failed" if error else "completed", capabilities=capabilities,
                                   error=error, elapsed_ms=(time.monotonic() - self._started) * 1000,
                                   stage_elapsed_ms=(time.monotonic() - self._stage_started) * 1000)
                self._active = False
                return

    def close(self) -> None:
        self._cancellation.set()
