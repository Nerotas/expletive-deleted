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
from .media import MEDIA_EXTENSIONS, archive_path, output_path, relative_media_path, transcript_path
from .models import (
    JobError,
    JobMode,
    JobRecord,
    JobStatus,
    JobSubmissionCode,
    JobSubmissionResult,
)


TERMINAL_STATUSES = {"completed", "failed", "cancelled", "transcribed"}


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

    def _configured_runtime_path(self, name: str, executable: Path | None) -> str | None:
        """Return a verified override or fail before any media processing begins."""
        if executable is None:
            return None
        status = inspect_executable(name.lower(), name, str(executable), FFMPEG_VERSION)
        if not status.ready or status.path is None:
            raise RuntimeError(
                f"Configured {name} is unavailable: {executable}. {status.detail}. "
                "Open Settings and choose a valid FFmpeg installation, then retry."
            )
        return str(status.path)

    def _run(self, job_id: str) -> None:
        cancellation = self._cancellations[job_id]
        source = self._jobs[job_id].source
        destination = output_path(
            source,
            self.settings.directories.output,
            self.settings.directories.input,
        )
        transcript = transcript_path(
            source,
            self.settings.directories.transcripts,
            self.settings.directories.input,
        )
        output_existed = destination.exists()
        processing_destination = destination
        if self._jobs[job_id].overwrite_output and output_existed:
            processing_destination = destination.with_name(
                f".{destination.stem}.{uuid4().hex}.partial{destination.suffix}"
            )
        try:
            if cancellation.is_set():
                self._set_status(job_id, "cancelled", message="Job cancelled")
                return
            if (
                self._jobs[job_id].mode == "censor"
                and destination.exists()
                and not self._jobs[job_id].overwrite_output
            ):
                raise JobSubmissionError(
                    "existing_output",
                    f"Output already exists: {destination}",
                )
            ffmpeg_bin = self._configured_runtime_path(
                "FFmpeg", self.settings.runtime.ffmpeg_path
            )
            ffprobe_bin = self._configured_runtime_path(
                "FFprobe", self.settings.runtime.ffprobe_path
            )
            destination.parent.mkdir(parents=True, exist_ok=True)

            with self._lock:
                self._set_status(job_id, "transcribing", percent=0.0)
            censor = self._censor_factory(
                str(source),
                str(processing_destination),
                self.settings.whisper.model,
                str(transcript.parent),
                whisper_library=self.settings.whisper.library,
                whisper_device=self.settings.processing.device,
                censor_method="karaoke"
                if self.settings.censoring.stereo_method == "karaoke"
                else "mute",
                padding_before_ms=self.settings.censoring.padding_before_ms,
                padding_after_ms=self.settings.censoring.padding_after_ms,
                surround_output=self.settings.audio.surround_output,
                video_mode=self.settings.video.mode,
                progress_callback=lambda progress: self._on_progress(job_id, progress),
                cancellation=cancellation,
                ffmpeg_bin=ffmpeg_bin,
                ffprobe_bin=ffprobe_bin,
                whisper_cache_dir=self.settings.runtime.whisper_cache,
            )
            process_options = {
                "report_only": self._jobs[job_id].mode == "report_only",
            }
            if self._jobs[job_id].force_transcribe:
                process_options["force_transcribe"] = True
            success = censor.process(**process_options)
            if cancellation.is_set():
                raise InterruptedError("Job cancelled")
            if not success:
                detail = getattr(censor, "last_error", None)
                raise RuntimeError(detail or "Processing engine reported failure")
            if not transcript.is_file():
                raise RuntimeError(
                    f"Processing completed without a verified transcript: {transcript}"
                )

            with self._lock:
                if self._jobs[job_id].mode == "report_only":
                    self._set_status(job_id, "transcribed", percent=100.0, message="Report completed")
                    return
                self._set_status(job_id, "verifying", percent=100.0)
            if not processing_destination.is_file():
                raise RuntimeError(f"Expected output was not created: {processing_destination}")
            if processing_destination != destination:
                processing_destination.replace(destination)
            if self.settings.source.archive_after_success:
                archive = archive_path(
                    source,
                    self.settings.directories.archive,
                    self.settings.directories.input,
                )
                if archive.exists():
                    raise RuntimeError(f"Archive destination already exists: {archive}")
                archive.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), archive)
            with self._lock:
                self._set_status(job_id, "completed", percent=100.0, message="Processing completed")
        except InterruptedError:
            self._remove_incomplete_output(processing_destination, destination, output_existed)
            with self._lock:
                self._set_status(job_id, "cancelled", message="Job cancelled")
        except Exception as exc:
            self._remove_incomplete_output(processing_destination, destination, output_existed)
            error = JobError(
                "processing_failed",
                "Media processing failed",
                str(exc),
                retryable=True,
                diagnostic=traceback.format_exc(),
            )
            with self._lock:
                self._set_status(job_id, "failed", error=error, message=error.message)

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
