"""Transport-independent application service used by CLI and future desktop APIs."""

from __future__ import annotations

import shutil
from uuid import uuid4
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

from backend.jobs import JobManager, JobMode, JobRecord, JobSubmissionResult
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
from .library import ArchiveItem, LibraryItem, scan_archive, scan_library


class ServiceBusyError(RuntimeError):
    """Raised when settings cannot change while jobs are active."""


class ArchiveSourceError(ValueError):
    """Raised when a Queue source cannot be archived safely."""


class ImportSourceError(ValueError):
    """Raised when a file cannot be safely copied into Ready."""


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

    def get_archive(self) -> tuple[ArchiveItem, ...]:
        return scan_archive(self.settings)

    def get_capabilities(self) -> dict[str, object]:
        return get_capabilities(self.settings)

    def submit_job(self, source: Path, mode: JobMode | None = None) -> JobRecord:
        return self.jobs.submit(source, mode)

    def submit_jobs(self, sources: list[Path], mode: JobMode) -> tuple[JobSubmissionResult, ...]:
        """Submit a selective batch while retaining ordered per-source results."""
        return self.jobs.submit_many(sources, mode)

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

    def import_sources(self, sources: list[Path]) -> list[dict[str, object]]:
        """Copy explicitly selected media to Ready without overwriting originals or targets."""
        ready = self.settings.directories.input.resolve()
        results: list[dict[str, object]] = []
        planned: set[Path] = set()
        for raw_source in sources:
            source = raw_source.expanduser().resolve()
            destination = ready / source.name
            if not source.is_file() or raw_source.is_symlink():
                results.append({"source": str(raw_source), "status": "unavailable", "detail": "File is unavailable or is a symbolic link"})
            elif source.suffix.lower() not in MEDIA_EXTENSIONS:
                results.append({"source": str(source), "status": "unsupported", "detail": "This file type is not supported"})
            elif destination.exists() or destination in planned:
                results.append({"source": str(source), "status": "already_exists", "detail": f"A file named {source.name} is already in Ready"})
            else:
                planned.add(destination)
                temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.partial")
                try:
                    shutil.copy2(source, temporary)
                    temporary.replace(destination)
                    results.append({"source": str(source), "status": "added", "destination": str(destination)})
                except OSError as exc:
                    temporary.unlink(missing_ok=True)
                    results.append({"source": str(source), "status": "failed", "detail": f"Could not copy file: {exc}"})
        return results

    def purge_archive_source(self, source: Path) -> dict[str, object]:
        """Permanently delete one archived original after an explicit UI confirmation."""
        self._ensure_no_active_jobs("Archived files cannot be deleted while a job is active")
        source = source.expanduser().resolve()
        archive_root = self.settings.directories.archive.resolve()
        try:
            relative_media_path(source, archive_root)
        except ValueError as exc:
            raise ArchiveSourceError(str(exc)) from exc
        if not source.is_file() or source.is_symlink() or source.suffix.lower() not in MEDIA_EXTENSIONS:
            raise ArchiveSourceError(f"Archive file is unavailable or unsupported: {source}")
        size_bytes = source.stat().st_size
        try:
            source.unlink()
            self._remove_empty_archive_parents(source.parent, archive_root)
        except OSError as exc:
            raise ArchiveSourceError(f"Could not delete archive file: {exc}") from exc
        return {"source": str(source), "deleted_bytes": size_bytes}

    def restore_archive_source(self, source: Path) -> dict[str, object]:
        """Move an archived original back to Ready without overwriting a Queue source."""
        self._ensure_no_active_jobs("Archived files cannot be returned while a job is active")
        raw_source = source.expanduser()
        if raw_source.is_symlink():
            raise ArchiveSourceError(f"Archive file is unavailable or unsupported: {raw_source}")
        source = raw_source.resolve()
        archive_root = self.settings.directories.archive.resolve()
        input_root = self.settings.directories.input.resolve()
        try:
            relative_path = relative_media_path(source, archive_root)
        except ValueError as exc:
            raise ArchiveSourceError(str(exc)) from exc
        if not source.is_file() or source.suffix.lower() not in MEDIA_EXTENSIONS:
            raise ArchiveSourceError(f"Archive file is unavailable or unsupported: {source}")

        destination = input_root / relative_path
        if destination.exists():
            raise ArchiveSourceError(f"Queue destination already exists: {destination}")
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), destination)
            self._remove_empty_archive_parents(source.parent, archive_root)
        except OSError as exc:
            raise ArchiveSourceError(f"Could not return archive file to Queue: {exc}") from exc
        return {"source": str(source), "restored_to": str(destination)}

    def purge_archive(self) -> dict[str, object]:
        """Permanently delete every supported original in Processed after confirmation."""
        self._ensure_no_active_jobs("Archived files cannot be deleted while a job is active")
        deleted_bytes = 0
        deleted_count = 0
        for item in self.get_archive():
            result = self.purge_archive_source(item.source)
            deleted_count += 1
            deleted_bytes += int(result["deleted_bytes"])
        return {"deleted_count": deleted_count, "deleted_bytes": deleted_bytes}

    def _ensure_no_active_jobs(self, message: str) -> None:
        active = tuple(
            job for job in self.jobs.list()
            if job.status not in ("completed", "failed", "cancelled", "transcribed")
        )
        if active:
            raise ServiceBusyError(message)

    @staticmethod
    def _remove_empty_archive_parents(directory: Path, archive_root: Path) -> None:
        while directory != archive_root:
            try:
                directory.rmdir()
            except OSError:
                return
            directory = directory.parent

    def close(self) -> None:
        self.jobs.close()
