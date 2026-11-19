"""Library-neutral loading and transcription for supported Whisper runtimes."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
import time
from typing import Any

from backend.runtime.dependency_inspection import (
    require_whisper_model_path,
)
from backend.runtime.devices import (
    get_whisper_device_status,
)
from backend.runtime.locations import (
    require_whisper_model,
)


SUPPORTED_WHISPER_LIBRARIES = ("faster-whisper",)


@dataclass(frozen=True)
class TranscriptionProgress:
    processed_seconds: float
    total_seconds: float
    elapsed_seconds: float

    @property
    def percent(self) -> float | None:
        # Leave completion to the caller, after the transcript has been verified.
        return min(99.0, self.processed_seconds / self.total_seconds * 100) if self.total_seconds > 0 else None

    @property
    def speed(self) -> float | None:
        return self.processed_seconds / self.elapsed_seconds if self.elapsed_seconds > 0 and self.processed_seconds > 0 else None

    @property
    def eta_seconds(self) -> float | None:
        speed = self.speed
        return max(0.0, self.total_seconds - self.processed_seconds) / speed if speed else None


def require_whisper_library(library: str) -> str:
    if library not in SUPPORTED_WHISPER_LIBRARIES:
        raise ValueError(
            f"Unsupported Whisper library {library!r}; choose one of: "
            f"{', '.join(SUPPORTED_WHISPER_LIBRARIES)}."
        )
    return library


def load_transcription_model(
    library: str,
    model_name: str,
    requested_device: str = "auto",
    cache_dir: Path | None = None,
) -> tuple[Any, str]:
    """Load a prepared model without permitting an implicit network download."""
    library = require_whisper_library(library)
    model_name = require_whisper_model(model_name)
    status = get_whisper_device_status(model_name, requested_device)
    model_path = require_whisper_model_path(cache_dir, library=library, model=model_name)

    from faster_whisper import WhisperModel

    model = WhisperModel(
        str(model_path),
        device=status.selected,
        compute_type=status.compute_type,
        local_files_only=True,
    )
    return model, status.selected


def transcribe_segments(
    model: Any,
    library: str,
    media_path: str,
    *,
    experimental_batch_size: int | None = None,
    check_cancelled: Callable[[], None] | None = None,
    on_prepared: Callable[[], None] | None = None,
    on_progress: Callable[[TranscriptionProgress], None] | None = None,
) -> Iterable[dict[str, Any]]:
    """Normalize standard output, or explicitly opt into the experimental pipeline.

    The 1.2.1 batched pipeline cannot condition on previous text or suppress
    silence hallucinations like standard inference. It is not an equivalent mode.
    Cancellation checkpoints cannot interrupt a native decoding call.
    """
    library = require_whisper_library(library)
    if experimental_batch_size is not None and (
        isinstance(experimental_batch_size, bool)
        or not isinstance(experimental_batch_size, int)
        or experimental_batch_size not in (1, 2, 4)
    ):
        raise ValueError("Experimental batch size must be 1, 2, or 4; omit it for standard inference.")
    if check_cancelled:
        check_cancelled()
    options: dict[str, Any] = {
        "language": "en", "word_timestamps": True, "vad_filter": True,
    }
    transcriber = model
    processed_seconds = 0.0
    total_seconds = 0.0
    inference_started = 0.0
    if experimental_batch_size is None:
        options.update(condition_on_previous_text=True, hallucination_silence_threshold=2.0)
    else:
        from importlib.metadata import version
        if version("faster-whisper") != "1.2.1":
            raise RuntimeError("The batching experiment requires faster-whisper 1.2.1; no automatic upgrade is allowed.")
        from faster_whisper import BatchedInferencePipeline

        if on_progress is not None:
            class ProgressPipeline(BatchedInferencePipeline):
                # The supported 1.2.1 forward call completes decoding and word alignment
                # for one batch, including chunks that produce no transcript segments.
                def forward(self, features, tokenizer, chunks_metadata, options):
                    nonlocal processed_seconds
                    if check_cancelled:
                        check_cancelled()
                    result = super().forward(features, tokenizer, chunks_metadata, options)
                    if check_cancelled:
                        check_cancelled()
                    processed_seconds += sum(chunk["duration"] for chunk in chunks_metadata)
                    on_progress(TranscriptionProgress(
                        min(processed_seconds, total_seconds), total_seconds,
                        time.perf_counter() - inference_started,
                    ))
                    return result

            transcriber = ProgressPipeline(model=model)
        else:
            transcriber = BatchedInferencePipeline(model=model)
        # A fresh wrapper avoids sharing its mutable timestamp state across runs.
        options["batch_size"] = experimental_batch_size
    try:
        output, info = transcriber.transcribe(media_path, **options)
        segments = iter(output)
    except RuntimeError as exc:
        if experimental_batch_size is None:
            raise
        raise RuntimeError(
            "Batched transcription could not start. If memory is limited, close other apps and retry. "
            f"No standard-mode retry was attempted. Details: {exc}"
        ) from exc
    try:
        if on_prepared:
            on_prepared()
        if experimental_batch_size is not None and on_progress is not None:
            total_seconds = info.duration_after_vad
            inference_started = time.perf_counter()
            on_progress(TranscriptionProgress(0.0, total_seconds, 0.0))
        while True:
            if check_cancelled:
                check_cancelled()
            try:
                segment = next(segments)
            except StopIteration:
                break
            except RuntimeError as exc:
                if experimental_batch_size is None:
                    raise
                raise RuntimeError(
                    "Batched transcription failed. If memory is limited, close other apps and retry. "
                    f"No standard-mode retry was attempted. Details: {exc}"
                ) from exc
            if check_cancelled:
                check_cancelled()
            yield {
                "text": segment.text,
                "start": segment.start,
                "end": segment.end,
                "words": [
                    {"word": word.word, "start": word.start, "end": word.end}
                    for word in (segment.words or [])
                ],
            }
    finally:
        close = getattr(segments, "close", None)
        if close is not None:
            close()
