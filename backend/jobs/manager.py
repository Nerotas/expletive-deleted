"""Serial, in-memory orchestration for application media jobs."""

from __future__ import annotations

import shutil
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Event, RLock
from typing import Callable
from uuid import uuid4

from backend.censor import ProfanityCensor
from backend.settings import AppSettings

from .events import JobEvent
from .media import MEDIA_EXTENSIONS, output_path
from .models import JobError, JobMode, JobRecord, JobStatus


class JobNotFoundError(KeyError):
    """Raised when a requested job id is unknown."""


class JobSubmissionError(ValueError):
    """Raised when a source cannot be submitted safely."""


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

    def submit(self, source: Path, mode: JobMode | None = None) -> JobRecord:
        source = source.expanduser().resolve()
        if not source.is_file():
            raise JobSubmissionError(f"Source file does not exist: {source}")
        if source.suffix.lower() not in MEDIA_EXTENSIONS:
            raise JobSubmissionError(f"Unsupported media type: {source.suffix or '(none)'}")
        selected_mode: JobMode = mode or self.settings.processing.mode
        job = JobRecord(uuid4().hex, source, selected_mode)
        cancellation = Event()
        with self._lock:
            self._jobs[job.id] = job
            self._events[job.id] = []
            self._cancellations[job.id] = cancellation
            self._emit(job.id, "stage", stage="queued", message="Job queued")
            self._futures[job.id] = self._executor.submit(self._run, job.id)
        return job

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
            if job.status in ("completed", "failed", "cancelled", "transcribed"):
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
        source = self._jobs[job_id].source
        destination = output_path(source, self.settings.directories.output)
        created_output = False
        try:
            if cancellation.is_set():
                self._set_status(job_id, "cancelled", message="Job cancelled")
                return
            if self._jobs[job_id].mode == "censor" and destination.exists():
                raise JobSubmissionError(f"Output already exists: {destination}")

            with self._lock:
                self._set_status(job_id, "transcribing", percent=0.0)
            censor = self._censor_factory(
                str(source),
                str(destination),
                "large",
                str(self.settings.directories.transcripts),
                censor_method="karaoke"
                if self.settings.censoring.stereo_method == "karaoke"
                else "mute",
                padding_before_ms=self.settings.censoring.padding_before_ms,
                padding_after_ms=self.settings.censoring.padding_after_ms,
                surround_output=self.settings.audio.surround_output,
                video_mode=self.settings.video.mode,
                progress_callback=lambda progress: self._on_progress(job_id, progress),
                cancellation=cancellation,
                ffmpeg_bin=str(self.settings.runtime.ffmpeg_path)
                if self.settings.runtime.ffmpeg_path
                else None,
                ffprobe_bin=str(self.settings.runtime.ffprobe_path)
                if self.settings.runtime.ffprobe_path
                else None,
                whisper_cache_dir=self.settings.runtime.whisper_cache,
            )
            success = censor.process(report_only=self._jobs[job_id].mode == "report_only")
            created_output = destination.exists()
            if cancellation.is_set():
                raise InterruptedError("Job cancelled")
            if not success:
                raise RuntimeError("Processing engine reported failure")

            with self._lock:
                if self._jobs[job_id].mode == "report_only":
                    self._set_status(job_id, "transcribed", percent=100.0, message="Report completed")
                    return
                self._set_status(job_id, "verifying", percent=100.0)
            if not destination.is_file():
                raise RuntimeError(f"Expected output was not created: {destination}")
            if self.settings.source.archive_after_success:
                archive = self.settings.directories.archive / source.name
                if archive.exists():
                    raise RuntimeError(f"Archive destination already exists: {archive}")
                shutil.move(str(source), archive)
            with self._lock:
                self._set_status(job_id, "completed", percent=100.0, message="Processing completed")
        except InterruptedError:
            if created_output or destination.exists():
                destination.unlink(missing_ok=True)
            with self._lock:
                self._set_status(job_id, "cancelled", message="Job cancelled")
        except Exception as exc:
            if created_output:
                destination.unlink(missing_ok=True)
            error = JobError(
                "processing_failed",
                "Media processing failed",
                str(exc),
                retryable=True,
            )
            with self._lock:
                self._set_status(job_id, "failed", error=error, message=error.message)