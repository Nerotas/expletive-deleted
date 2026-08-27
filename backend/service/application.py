"""Transport-independent application service used by CLI and future desktop APIs."""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

from backend.jobs import JobManager, JobMode, JobRecord
from backend.jobs.media import MEDIA_EXTENSIONS, archive_path, relative_media_path
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


class ArchiveSourceError(ValueError):
    """Raised when a Queue source cannot be archived safely."""


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

    def archive_source(self, source: Path) -> dict[str, object]:
        """Move a completed or transcribed source out of the Queue without touching artifacts."""
        active = tuple(
            job for job in self.jobs.list()
            if job.status not in ("completed", "failed", "cancelled", "transcribed")
        )
        if active:
            raise ServiceBusyError("Files cannot be archived while jobs are active")

        source = source.expanduser().resolve()
        input_root = self.settings.directories.input.resolve()
        try:
            relative_media_path(source, input_root)
        except ValueError as exc:
            raise ArchiveSourceError(str(exc)) from exc
        if not source.is_file() or source.suffix.lower() not in MEDIA_EXTENSIONS:
            raise ArchiveSourceError(f"Queue source is unavailable or unsupported: {source}")

        item = next((candidate for candidate in self.get_library() if candidate.source.resolve() == source), None)
        if item is None or item.status not in ("transcribed", "finished"):
            raise ArchiveSourceError("Only transcribed or finished Queue files can be archived")

        destination = archive_path(source, self.settings.directories.archive, input_root)
        if destination.exists():
            raise ArchiveSourceError(f"Archive destination already exists: {destination}")
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), destination)
        except OSError as exc:
            raise ArchiveSourceError(f"Could not archive source: {exc}") from exc
        return {"source": str(source), "archived_to": str(destination)}

    def close(self) -> None:
        self.jobs.close()
