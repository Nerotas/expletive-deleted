"""Serial, in-memory orchestration for application media jobs."""

from __future__ import annotations

import shutil
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Event, RLock
from typing import Callable
from uuid import uuid4

from backend.censor import ProfanityCensor
from backend.runtime import FFMPEG_VERSION, inspect_executable
from backend.settings import AppSettings

from .events import JobEvent
from .media import MEDIA_EXTENSIONS, output_path, relative_media_path
from .models import (
    JobError,
    JobMode,
    JobRecord,
    JobStatus,
    JobSubmissionCode,
    JobSubmissionResult,
    TERMINAL_STATUSES,
)
from .runtime import JobRuntime


class JobNotFoundError(KeyError):
    """Raised when a requested job id is unknown."""


class JobSubmissionError(ValueError):
    """Raised when a source cannot be submitted safely."""

    def __init__(self, code: JobSubmissionCode, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(detail)


class JobManager:
    """Run submitted jobs serially and expose polling-friendly records and events."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        censor_factory: Callable[..., ProfanityCensor] = ProfanityCensor,
    ):
        settings.validate()
        self.settings = settings
        self._censor_factory = censor_factory
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="profanity-job")
        self._lock = RLock()
        self._jobs: dict[str, JobRecord] = {}
        self._events: dict[str, list[JobEvent]] = {}
        self._cancellations: dict[str, Event] = {}
        self._futures: dict[str, Future[None]] = {}
        self._sequence = 0
        self._runtime = JobRuntime(
            settings,
            censor_factory=censor_factory,
            on_progress=self._on_progress,
            on_status=self._set_status_callback,
            get_job=lambda job_id: self._jobs[job_id],
            get_source=lambda job_id: self._jobs[job_id].source,
        )

    def submit(
        self,
        source: Path,
        mode: JobMode | None = None,
        *,
        force_transcribe: bool = False,
        overwrite_output: bool = False,
    ) -> JobRecord:
        source = source.expanduser().resolve()
        selected_mode = mode or self.settings.processing.mode
        if selected_mode not in ("report_only", "censor"):
            raise JobSubmissionError("invalid_mode", f"Unsupported processing mode: {selected_mode}")
        try:
            relative_media_path(source, self.settings.directories.input)
        except ValueError as exc:
            raise JobSubmissionError("outside_input", str(exc)) from exc
        if not source.is_file():
            raise JobSubmissionError("unavailable", f"Source file does not exist: {source}")
        if source.suffix.lower() not in MEDIA_EXTENSIONS:
            raise JobSubmissionError(
                "unsupported",
                f"Unsupported media type: {source.suffix or '(none)'}",
            )
        if force_transcribe and selected_mode != "report_only":
            raise JobSubmissionError(
                "invalid_mode",
                "A fresh transcript can only be requested for a transcript-only job",
            )
        if overwrite_output and selected_mode != "censor":
            raise JobSubmissionError(
                "invalid_mode",
                "Output replacement can only be requested for a censor job",
            )
        job = JobRecord(
            uuid4().hex,
            source,
            selected_mode,
            force_transcribe=force_transcribe,
            overwrite_output=overwrite_output,
        )
        cancellation = Event()
        with self._lock:
            if any(
                existing.source == source and existing.status not in TERMINAL_STATUSES
                for existing in self._jobs.values()
            ):
                raise JobSubmissionError(
                    "already_queued",
                    f"A job is already queued or running for {source.name}",
                )
            if selected_mode == "censor" and not overwrite_output and output_path(
                source,
                self.settings.directories.output,
                self.settings.directories.input,
            ).exists():
                raise JobSubmissionError(
                    "existing_output",
                    f"Output already exists for {source.name}",
                )
            self._jobs[job.id] = job
            self._events[job.id] = []
            self._cancellations[job.id] = cancellation
            self._emit(job.id, "stage", stage="queued", message="Job queued")
            self._futures[job.id] = self._executor.submit(self._run, job.id)
        return job

    def submit_many(
        self,
        sources: list[Path] | tuple[Path, ...],
        mode: JobMode,
    ) -> tuple[JobSubmissionResult, ...]:
        """Queue valid sources in request order and retain per-source rejections."""
        if mode not in ("report_only", "censor"):
            raise JobSubmissionError("invalid_mode", f"Unsupported processing mode: {mode}")

        results: list[JobSubmissionResult] = []
        for raw_source in sources:
            source = raw_source.expanduser().resolve()
            try:
                job = self.submit(source, mode)
                results.append(JobSubmissionResult(source, "queued", job=job))
            except JobSubmissionError as exc:
                results.append(
                    JobSubmissionResult(
                        source,
                        "rejected",
                        code=exc.code,
                        detail=exc.detail,
                    )
                )
        return tuple(results)

    def get(self, job_id: str) -> JobRecord:
        with self._lock:
            try:
                return self._jobs[job_id]
            except KeyError as exc:
                raise JobNotFoundError(job_id) from exc

    def list(self) -> tuple[JobRecord, ...]:
        with self._lock:
            return tuple(self._jobs.values())

    def events(self, job_id: str, after_sequence: int = 0) -> tuple[JobEvent, ...]:
        with self._lock:
            if job_id not in self._jobs:
                raise JobNotFoundError(job_id)
            return tuple(event for event in self._events[job_id] if event.sequence > after_sequence)

    def cancel(self, job_id: str) -> JobRecord:
        with self._lock:
            job = self.get(job_id)
            if job.status in TERMINAL_STATUSES:
                return job
            self._cancellations[job_id].set()
            future = self._futures[job_id]
            if future.cancel():
                self._set_status(job_id, "cancelled", message="Job cancelled before processing")
            return self._jobs[job_id]

    def wait(self, job_id: str, timeout: float | None = None) -> JobRecord:
        with self._lock:
            if job_id not in self._jobs:
                raise JobNotFoundError(job_id)
            future = self._futures[job_id]
        if not future.cancelled():
            future.result(timeout=timeout)
        return self.get(job_id)

    def close(self, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=not wait)

    def _emit(self, job_id: str, event: str, **values: object) -> JobEvent:
        self._sequence += 1
        item = JobEvent(event, job_id, sequence=self._sequence, **values)
        self._events[job_id].append(item)
        return item

    def _set_status_callback(
        self,
        job_id: str,
        status: JobStatus,
        percent: float | None = None,
        error: JobError | None = None,
        message: str | None = None,
    ) -> JobRecord:
        with self._lock:
            return self._set_status(job_id, status, percent=percent, error=error, message=message)

    def _set_status(
        self,
        job_id: str,
        status: JobStatus,
        *,
        percent: float | None = None,
        error: JobError | None = None,
        message: str | None = None,
    ) -> JobRecord:
        current = self._jobs[job_id]
        updated = replace(current, status=status, progress_percent=percent, error=error)
        self._jobs[job_id] = updated
        event_type = "error" if error else "completed" if status in ("completed", "transcribed") else "stage"
        self._emit(job_id, event_type, stage=status, percent=percent, error=error, message=message)
        return updated

    def _on_progress(self, job_id: str, progress: dict[str, object]) -> None:
        with self._lock:
            if progress.get("event") == "detection":
                self._emit(
                    job_id,
                    "detection",
                    stage="transcribing",
                    word=progress.get("word"),
                    start=progress.get("start"),
                    end=progress.get("end"),
                )
                return
            stage = progress.get("stage")
            status: JobStatus = "censoring" if stage == "censoring" else "transcribing"
            percent_value = progress.get("percent")
            percent = float(percent_value) if isinstance(percent_value, (int, float)) else None
            current = self._jobs[job_id]
            if current.status != status:
                self._set_status(job_id, status, percent=percent)
            else:
                self._jobs[job_id] = replace(current, progress_percent=percent)
            self._emit(
                job_id,
                "progress",
                stage=status,
                percent=percent,
                eta_seconds=progress.get("eta_seconds"),
                fps=progress.get("fps"),
                message=progress.get("message"),
            )

    def _run(self, job_id: str) -> None:
        cancellation = self._cancellations[job_id]
        self._runtime.run(job_id, cancellation)

    @staticmethod
    def _remove_incomplete_output(
        processing_destination: Path,
        destination: Path,
        output_existed: bool,
    ) -> None:
        if processing_destination != destination:
            processing_destination.unlink(missing_ok=True)
        elif not output_existed:
            destination.unlink(missing_ok=True)
