"""Transport-independent application service used by CLI and future desktop APIs."""

from __future__ import annotations

from functools import wraps
from dataclasses import replace
from threading import RLock
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

from backend.jobs import JobManager, JobMode, JobRecord, JobSubmissionResult
from backend.jobs.downloads import DownloadManager, DownloadRecord
from backend.jobs.media import MEDIA_EXTENSIONS, archive_path, relative_media_path
from backend.settings import (
    AppSettings,
    DirectoryAccessError,
    SettingsStore,
    ensure_directories,
    load_effective_settings,
    settings_from_dict,
    settings_to_dict,
)

from backend.settings.transactions import snapshot, changes_between, validate_base
from backend.settings.resolver import effective_settings

from .capabilities import get_capabilities
from .library import ArchiveItem, LibraryItem, scan_archive, scan_library
from backend.settings.directories import bind_directories
from backend.filesystem.operations import remove_file, remove_empty_parents
from backend.filesystem.publication import move_verified
from backend.filesystem.paths import identity, version


class ServiceBusyError(RuntimeError):
    code = "settings_busy"
    """Raised when settings cannot change while jobs are active."""


class ArchiveSourceError(ValueError):
    """Raised when a Queue source cannot be archived safely."""


class ImportSourceError(ValueError):
    """Raised when a file cannot be safely copied into Ready."""


def _while_open(operation: Callable[..., Any]) -> Callable[..., Any]:
    """Serialize submissions with settings replacement, including metadata lookup."""
    @wraps(operation)
    def guarded(self, *args, **kwargs):
        with self._lifecycle_lock:
            if self._closing:
                raise ServiceBusyError("The local processing service is closing")
            return operation(self, *args, **kwargs)
    return guarded


def _settings_locked(operation):
    @wraps(operation)
    def guarded(self, *args, **kwargs):
        with self.store.locked():
            return operation(self, *args, **kwargs)
    return guarded


class BackendService:
    """Own settings and one serial job manager behind a stable callable boundary."""

    def __init__(
        self,
        store: SettingsStore | None = None,
        *,
        manager_factory: Callable[[AppSettings], JobManager] = JobManager,
    ):
        self._lifecycle_lock = RLock()
        self._closing = False
        self.store = store or SettingsStore()
        self._manager_factory = manager_factory
        self.settings = load_effective_settings(self.store)
        try:
            ensure_directories(self.settings.directories)
        except DirectoryAccessError:
            # Keep Settings reachable for explicit folder reselection. Every media
            # operation still validates the persisted binding before touching media.
            pass
        self.jobs = manager_factory(self.settings)
        self.downloads = DownloadManager(self.settings, self._queue_completed_youtube_download)

    def get_settings(self) -> dict[str, object]:
        return settings_to_dict(self.settings)

    @_while_open
    def output_context(self):
        """Snapshot current output ownership without holding a settings lock during probing."""
        return self.settings, tuple(self.jobs.list())

    @_while_open
    def get_settings_snapshot(self):
        return self.store.snapshot(effective_settings)

    @_while_open
    def update_settings(self, payload: Mapping[str, Any], base=None):
        # Internal compatibility callers edit the service snapshot; IPC requires an explicit base.
        baseline = validate_base(base) if base is not None else snapshot(self.settings)
        result = self.patch_settings(baseline["revision"], changes_between(baseline["settings"], payload))
        return result if base is not None else result["snapshot"]["settings"]

    @_while_open
    @_settings_locked
    def patch_settings(self, revision, changes, *, strict=False):
        self._ensure_settings_idle()
        replacements = []

        def prepare(updated):
            updated = replace(updated, directories=bind_directories(updated.directories))
            ensure_directories(effective_settings(updated).directories)
            effective = effective_settings(updated)
            # Construct replacements before publication so failure leaves old managers usable.
            jobs = self._manager_factory(effective)
            replacements.append(jobs)
            downloads = DownloadManager(effective, self._queue_completed_youtube_download)
            replacements.append(downloads)
            return updated

        try:
            result = self.store.transact(revision, changes, effective=effective_settings, prepare=prepare, strict=strict)
        except Exception:
            for manager in replacements:
                manager.close()
            raise
        if result["status"] == "saved":
            old_jobs, old_downloads = self.jobs, self.downloads
            self.settings = effective_settings(self.store.load())
            self.jobs, self.downloads = replacements
            old_jobs.close()
            old_downloads.close()
        return result

    def _ensure_settings_idle(self):
        active = any(job.status not in ("completed", "failed", "cancelled", "transcribed") for job in self.jobs.list())
        downloads_active = any(item.status not in ("completed", "failed", "cancelled") for item in self.downloads.list())
        if active or downloads_active:
            raise ServiceBusyError("Settings cannot change while jobs or downloads are active")

    def apply_runtime_changes(self, baseline, values, *, strict=False):
        allowed = {"ffmpeg_path", "ffprobe_path", "whisper_cache", "ytdlp_path"}
        if not set(values) <= allowed:
            raise ValueError("Unsupported verified runtime field")
        if bool("ffmpeg_path" in values) != bool("ffprobe_path" in values):
            raise ValueError("FFmpeg and FFprobe must be applied as a verified pair")
        changes = [{"field": f"runtime.{key}", "expected": baseline["settings"]["runtime"][key], "value": value}
                   for key, value in values.items()]
        if "whisper_cache" in values:
            changes.append({"field": "whisper.model", "expected": baseline["settings"]["whisper"]["model"],
                            "value": baseline["settings"]["whisper"]["model"]})
        return self.patch_settings(baseline["revision"], changes, strict=strict)

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

    @_while_open
    def submit_job(
        self,
        source: Path,
        mode: JobMode | None = None,
        *,
        force_transcribe: bool = False,
        overwrite_output: bool = False,
    ) -> JobRecord:
        return self.jobs.submit(
            source,
            mode,
            force_transcribe=force_transcribe,
            overwrite_output=overwrite_output,
        )

    @_while_open
    def submit_jobs(self, sources: list[Path], mode: JobMode) -> tuple[JobSubmissionResult, ...]:
        """Submit a selective batch while retaining ordered per-source results."""
        return self.jobs.submit_many(sources, mode)

    @_while_open
    def submit_youtube_download(self, url: str, retry_id: str | None = None, cookie_browser: str | None = None) -> DownloadRecord:
        return self.downloads.submit(url, retry_id, cookie_browser)

    def _queue_completed_youtube_download(self, source: Path) -> None:
        with self._lifecycle_lock:
            if not self._closing:
                self.jobs.submit(source, "report_only", auto_censor_after_transcription=True)

    @_while_open
    def archive_source(self, source: Path) -> dict[str, object]:
        """Move a completed or transcribed source out of the Queue without touching artifacts."""
        if source.expanduser().is_symlink():
            raise ArchiveSourceError('Select an original file rather than a symbolic link')
        source = source.expanduser().resolve()
        if any(
            job.source.expanduser().resolve() == source
            and job.status not in ("completed", "failed", "cancelled", "transcribed")
            for job in self.jobs.list()
        ):
            raise ServiceBusyError("This file cannot be archived while it is queued or processing")
        input_root = self.settings.directories.input.resolve()
        try:
            relative_media_path(source, input_root)
        except ValueError as exc:
            raise ArchiveSourceError(str(exc)) from exc
        if not source.is_file() or source.suffix.lower() not in MEDIA_EXTENSIONS:
            raise ArchiveSourceError(f"Queue source is unavailable or unsupported: {source}")

        selected_version = version(source)
        item = next((candidate for candidate in self.get_library() if candidate.source.resolve() == source), None)
        if item is None or item.status not in ("transcribed", "finished"):
            raise ArchiveSourceError("Only transcribed or finished Queue files can be archived")

        destination = archive_path(source, self.settings.directories.archive, input_root)
        if destination.exists():
            raise ArchiveSourceError(f"Archive destination already exists: {destination}")
        try:
            move_verified(self.settings.directories.binding(self.settings.directories.input), source,
                          self.settings.directories.binding(self.settings.directories.archive), destination, expected_version=selected_version)
        except (OSError, ValueError, RuntimeError) as exc:
            raise ArchiveSourceError(f"Could not archive source: {exc}") from exc
        return {"source": str(source), "archived_to": str(destination)}

    @_while_open
    def import_sources(self, sources: list[Path]) -> list[dict[str, object]]:
        """Queue a copy job for each selected file and report the accepted import."""
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
                try:
                    job = self.jobs.submit(source, "copy")
                    results.append({
                        "source": str(source),
                        "status": "added",
                        "destination": str(destination),
                        "job_id": job.id,
                    })
                except Exception as exc:  # pragma: no cover - surfaced to UI as a rejected import
                    results.append({"source": str(source), "status": "failed", "detail": str(exc)})
        return results

    @_while_open
    def purge_archive_source(self, source: Path) -> dict[str, object]:
        """Permanently delete one archived original after an explicit UI confirmation."""
        self._ensure_no_active_jobs("Archived files cannot be deleted while a job is active")
        if source.expanduser().is_symlink():
            raise ArchiveSourceError('Select an original file rather than a symbolic link')
        source = source.expanduser().resolve()
        archive_root = self.settings.directories.archive.resolve()
        try:
            relative_media_path(source, archive_root)
        except ValueError as exc:
            raise ArchiveSourceError(str(exc)) from exc
        if not source.is_file() or source.is_symlink() or source.suffix.lower() not in MEDIA_EXTENSIONS:
            raise ArchiveSourceError(f"Archive file is unavailable or unsupported: {source}")
        size_bytes = source.stat().st_size
        selected_identity = identity(source)
        try:
            remove_file(self.settings.directories.binding(self.settings.directories.archive), source, expected=selected_identity)
            remove_empty_parents(self.settings.directories.binding(self.settings.directories.archive), source.parent)
        except OSError as exc:
            raise ArchiveSourceError(f"Could not delete archive file: {exc}") from exc
        return {"source": str(source), "deleted_bytes": size_bytes}

    @_while_open
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
            move_verified(self.settings.directories.binding(self.settings.directories.archive), source,
                          self.settings.directories.binding(self.settings.directories.input), destination)
            remove_empty_parents(self.settings.directories.binding(self.settings.directories.archive), source.parent)
        except OSError as exc:
            raise ArchiveSourceError(f"Could not return archive file to Queue: {exc}") from exc
        return {"source": str(source), "restored_to": str(destination)}

    @_while_open
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
        if active or any(item.status not in ("completed", "failed", "cancelled") for item in self.downloads.list()):
            raise ServiceBusyError(message)

    def close(self) -> None:
        with self._lifecycle_lock:
            self._closing = True
        # Stop both lanes before waiting; callbacks must not queue work during exit.
        self.jobs.close(wait=False)
        self.downloads.close()
        self.jobs.close()
