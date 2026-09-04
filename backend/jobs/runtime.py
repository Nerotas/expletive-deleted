from __future__ import annotations

import shutil
import traceback
from pathlib import Path
from threading import Event
from typing import Callable
from uuid import uuid4

from backend.runtime import FFMPEG_VERSION, inspect_executable
from backend.settings import AppSettings

from .media import archive_path, output_path, transcript_path
from .models import JobError, JobStatus


class JobRuntime:
    """Run one media job and own the cleanup, state, and progress conversions."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        censor_factory: Callable[..., object],
        on_progress: Callable[[str, dict[str, object]], None],
        on_status: Callable[[str, JobStatus, float | None, JobError | None, str | None], None],
        get_job: Callable[[str], object],
        get_source: Callable[[str], Path],
    ):
        self.settings = settings
        self._censor_factory = censor_factory
        self._on_progress = on_progress
        self._on_status = on_status
        self._get_job = get_job
        self._get_source = get_source

    def run(self, job_id: str, cancellation: Event) -> None:
        source = self._current_source(job_id)
        job = self._current_job(job_id)

        if job.mode == "copy":
            destination = self.settings.directories.input.resolve() / source.name
            output_existed = destination.exists()
            processing_destination = destination.with_name(f".{destination.name}.{uuid4().hex}.partial")
            try:
                if cancellation.is_set():
                    self._on_status(job_id=job_id, status="cancelled", percent=None, error=None, message="Job cancelled")
                    return
                source_size = source.stat().st_size
                destination.parent.mkdir(parents=True, exist_ok=True)
                self._on_status(job_id=job_id, status="copying", percent=0.0, error=None, message="Copying to Ready")
                bytes_copied = 0
                last_update = 0.0
                with source.open("rb") as infile, processing_destination.open("wb") as outfile:
                    while True:
                        if cancellation.is_set():
                            raise InterruptedError("Job cancelled")
                        chunk = infile.read(1024 * 1024)
                        if not chunk:
                            break
                        outfile.write(chunk)
                        bytes_copied += len(chunk)
                        percent = 100.0 if source_size == 0 else min(100.0, (bytes_copied / source_size) * 100.0)
                        if percent >= last_update + 5.0 or percent >= 99.0:
                            self._on_progress(job_id, {"event": "progress", "stage": "copying", "percent": percent})
                            last_update = percent
                shutil.copystat(source, processing_destination, follow_symlinks=False)
                if destination.exists():
                    raise RuntimeError(f"A file named {source.name} is already in Ready")
                processing_destination.replace(destination)
                self._on_status(job_id=job_id, status="completed", percent=100.0, error=None, message="Copy completed")
            except InterruptedError:
                self._remove_incomplete_output(processing_destination, destination, output_existed)
                self._on_status(job_id=job_id, status="cancelled", percent=None, error=None, message="Job cancelled")
            except Exception as exc:
                self._remove_incomplete_output(processing_destination, destination, output_existed)
                error = JobError(
                    "copy_failed",
                    "Copy failed",
                    str(exc),
                    retryable=True,
                    diagnostic=traceback.format_exc(),
                )
                self._on_status(job_id=job_id, status="failed", percent=None, error=error, message=error.message)
            return

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
        if job.overwrite_output and output_existed:
            processing_destination = destination.with_name(
                f".{destination.stem}.{uuid4().hex}.partial{destination.suffix}"
            )
        try:
            if cancellation.is_set():
                self._on_status(job_id=job_id, status="cancelled", percent=None, error=None, message="Job cancelled")
                return
            if (
                job.mode == "censor"
                and destination.exists()
                and not job.overwrite_output
            ):
                raise RuntimeError(f"Output already exists: {destination}")

            ffmpeg_bin = self._configured_runtime_path("FFmpeg", self.settings.runtime.ffmpeg_path)
            ffprobe_bin = self._configured_runtime_path("FFprobe", self.settings.runtime.ffprobe_path)
            destination.parent.mkdir(parents=True, exist_ok=True)

            self._on_status(job_id=job_id, status="transcribing", percent=0.0, error=None, message=None)
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
                progress_callback=lambda progress: self._on_progress(job_id, progress),
                cancellation=cancellation,
                ffmpeg_bin=ffmpeg_bin,
                ffprobe_bin=ffprobe_bin,
                whisper_cache_dir=self.settings.runtime.whisper_cache,
            )
            process_options = {"report_only": job.mode == "report_only"}
            if job.force_transcribe:
                process_options["force_transcribe"] = True
            success = censor.process(**process_options)
            if cancellation.is_set():
                raise InterruptedError("Job cancelled")
            if not success:
                detail = getattr(censor, "last_error", None)
                raise RuntimeError(detail or "Processing engine reported failure")
            if not transcript.is_file():
                raise RuntimeError(f"Processing completed without a verified transcript: {transcript}")

            if job.mode == "report_only":
                self._on_status(job_id=job_id, status="transcribed", percent=100.0, error=None, message="Report completed")
                return

            self._on_status(job_id=job_id, status="verifying", percent=100.0, error=None, message=None)
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
            self._on_status(job_id=job_id, status="completed", percent=100.0, error=None, message="Processing completed")
        except InterruptedError:
            self._remove_incomplete_output(processing_destination, destination, output_existed)
            self._on_status(job_id=job_id, status="cancelled", percent=None, error=None, message="Job cancelled")
        except Exception as exc:
            self._remove_incomplete_output(processing_destination, destination, output_existed)
            error = JobError(
                "processing_failed",
                "Media processing failed",
                str(exc),
                retryable=True,
                diagnostic=traceback.format_exc(),
            )
            self._on_status(job_id=job_id, status="failed", percent=None, error=error, message=error.message)

    def _current_job(self, job_id: str):
        return self._get_job(job_id)

    def _current_source(self, job_id: str) -> Path:
        return self._get_source(job_id)

    def _configured_runtime_path(self, name: str, executable: Path | None) -> str | None:
        if executable is None:
            return None
        status = inspect_executable(name.lower(), name, str(executable), FFMPEG_VERSION)
        if not status.ready or status.path is None:
            raise RuntimeError(
                f"Configured {name} is unavailable: {executable}. {status.detail}. "
                "Open Settings and choose a valid FFmpeg installation, then retry."
            )
        return str(status.path)

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
