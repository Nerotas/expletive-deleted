from __future__ import annotations

from contextlib import ExitStack
import traceback
from pathlib import Path
from threading import Event
from typing import Callable

from backend.runtime import FFMPEG_VERSION, inspect_executable, resolve_whisper_cache_dir
from backend.settings import AppSettings
from backend.filesystem.operations import locked_file
from backend.filesystem.publication import Publication, copy_verified, move_verified
from backend.filesystem.paths import version, PathSafetyError

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
        source, job = self._current_source(job_id), self._current_job(job_id)
        directories = self.settings.directories
        published = False
        try:
            if job.mode == "copy":
                destination = directories.input / source.name
                with Publication(directories.binding(directories.input), destination, source=source,
                                 cancellation=cancellation) as publication:
                    self._on_status(job_id, "copying", 0.0, None, "Copying to Ready")
                    copy_verified(source, publication, lambda copied, size: self._on_progress(job_id, {
                        "event": "progress", "stage": "copying", "percent": 100.0 * copied / max(1, size),
                    }), expected_version=job.source_version)
                self._on_status(job_id, "completed", 100.0, None, "Copy completed")
                return

            destination = output_path(source, directories.output, directories.input)
            transcript = transcript_path(source, directories.transcripts, directories.input)
            with ExitStack() as resources:
                resources.enter_context(locked_file(directories.binding(directories.input), source))
                if job.source_version and version(source) != job.source_version:
                    raise PathSafetyError('Source changed while queued; select it again before processing')
                resources.enter_context(directories.binding(directories.transcripts).lease(transcript, create_parent=True))
                if cancellation.is_set():
                    raise InterruptedError("Job cancelled")
                publication = None
                if job.mode == "censor":
                    if not transcript.is_file():
                        raise RuntimeError(f"A verified transcript is required before censoring: {transcript}. Queue a transcript-only job first.")
                    publication = resources.enter_context(Publication(
                        directories.binding(directories.output), destination, source=source,
                        overwrite=job.overwrite_output, cancellation=cancellation,
                        expected_version=job.output_version,
                    ))
                censor = self._censor_factory(
                    str(source), str(publication.stage if publication else destination),
                    self.settings.whisper.model, str(transcript.parent),
                    whisper_library=self.settings.whisper.library,
                    whisper_device=self.settings.processing.device,
                    censor_method="karaoke" if self.settings.censoring.stereo_method == "karaoke" else "mute",
                    padding_before_ms=self.settings.censoring.padding_before_ms,
                    padding_after_ms=self.settings.censoring.padding_after_ms,
                    surround_output=self.settings.audio.surround_output,
                    video_mode=self.settings.video.mode,
                    progress_callback=lambda progress: self._on_progress(job_id, progress),
                    cancellation=cancellation,
                    ffmpeg_bin=self._configured_runtime_path("FFmpeg", self.settings.runtime.ffmpeg_path),
                    ffprobe_bin=self._configured_runtime_path("FFprobe", self.settings.runtime.ffprobe_path),
                    whisper_cache_dir=resolve_whisper_cache_dir(self.settings.runtime.whisper_cache),
                )
                if job.mode == "report_only":
                    self._on_status(job_id, "transcribing", 0.0, None, None)
                    options = {"report_only": True}
                    if job.force_transcribe:
                        options["force_transcribe"] = True
                    success = censor.process(**options)
                else:
                    self._on_status(job_id, "censoring", 0.0, None, "Using verified transcript")
                    success = censor.process_verified_transcript()
                if cancellation.is_set():
                    raise InterruptedError("Job cancelled")
                if not success:
                    raise RuntimeError(getattr(censor, "last_error", None) or "Processing engine reported failure")
                if job.mode == "report_only":
                    if not transcript.is_file():
                        raise RuntimeError(f"Processing completed without a verified transcript: {transcript}")
                else:
                    self._on_status(job_id, "verifying", 100.0, None, None)
                    publication.publish(lambda _: censor.verify_output())
                    published = True
            # Release the read lease before obtaining DELETE access for optional archiving.
            if job.mode == "report_only":
                self._on_status(job_id, "transcribed", 100.0, None, "Report completed")
                return
            if self.settings.source.archive_after_success:
                archive = archive_path(source, directories.archive, directories.input)
                move_verified(directories.binding(directories.input), source,
                              directories.binding(directories.archive), archive, expected_version=job.source_version)
            self._on_status(job_id, "completed", 100.0, None, "Processing completed")
        except InterruptedError:
            self._on_status(job_id, "cancelled", None, None, "Job cancelled")
        except Exception as exc:
            code = "archive_failed" if published else getattr(exc, "code", "copy_failed" if job.mode == "copy" else "processing_failed")
            message = "Output saved; original could not be archived" if published else "Copy failed" if job.mode == "copy" else "Media processing failed"
            error = JobError(code, message, str(exc), retryable=True, diagnostic=traceback.format_exc())
            self._on_status(job_id, "failed", None, error, error.message)

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
