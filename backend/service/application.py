"""Transport-independent application service used by CLI and future desktop APIs."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

from backend.jobs import JobManager, JobMode, JobRecord
from backend.settings import (
    AppSettings,
    SettingsStore,
    ensure_directories,
    load_effective_settings,
    settings_from_dict,
    settings_to_dict,
)

from .capabilities import get_capabilities
from .library import LibraryItem, scan_library


class ServiceBusyError(RuntimeError):
    """Raised when settings cannot change while jobs are active."""


class BackendService:
    """Own settings and one serial job manager behind a stable callable boundary."""

    def __init__(
        self,
        store: SettingsStore | None = None,
        *,
        manager_factory: Callable[[AppSettings], JobManager] = JobManager,
    ):
        self.store = store or SettingsStore()
        self._manager_factory = manager_factory
        self.settings = load_effective_settings(self.store)
        ensure_directories(self.settings.directories)
        self.jobs = manager_factory(self.settings)

    def get_settings(self) -> dict[str, object]:
        return settings_to_dict(self.settings)

    def update_settings(self, payload: Mapping[str, Any]) -> dict[str, object]:
        active = tuple(
            job for job in self.jobs.list()
            if job.status not in ("completed", "failed", "cancelled", "transcribed")
        )
        if active:
            raise ServiceBusyError("Settings cannot change while jobs are active")
        updated = settings_from_dict(payload, self.settings)
        ensure_directories(updated.directories)
        self.store.save(updated)
        self.jobs.close()
        self.settings = updated
        self.jobs = self._manager_factory(updated)
        return settings_to_dict(updated)

    def get_library(self) -> tuple[LibraryItem, ...]:
        return scan_library(
            self.settings,
            ffprobe_bin=str(self.settings.runtime.ffprobe_path)
            if self.settings.runtime.ffprobe_path
            else None,
        )

    def get_capabilities(self) -> dict[str, object]:
        return get_capabilities(self.settings)

    def submit_job(self, source: Path, mode: JobMode | None = None) -> JobRecord:
        return self.jobs.submit(source, mode)

    def close(self) -> None:
        self.jobs.close()