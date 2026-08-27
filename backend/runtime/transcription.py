"""Library-neutral loading and transcription for supported Whisper runtimes."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .dependencies import require_whisper_model_path
from .environment import get_whisper_device_status, require_whisper_model


SUPPORTED_WHISPER_LIBRARIES = ("faster-whisper", "openai-whisper")


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

    if library == "faster-whisper":
        from faster_whisper import WhisperModel

        model = WhisperModel(
            str(model_path),
            device=status.selected,
            compute_type=status.compute_type,
            local_files_only=True,
        )
    else:
        import whisper

        model = whisper.load_model(str(model_path), device=status.selected)
    return model, status.selected


def transcribe_segments(model: Any, library: str, media_path: str) -> Iterable[dict[str, Any]]:
    """Yield normalized segment dictionaries with optional word timestamps."""
    library = require_whisper_library(library)
    if library == "faster-whisper":
        segments = model.transcribe(
            media_path,
            language="en",
            word_timestamps=True,
            condition_on_previous_text=True,
            hallucination_silence_threshold=2.0,
            vad_filter=True,
        )[0]
        for segment in segments:
            yield {
                "text": segment.text,
                "start": segment.start,
                "end": segment.end,
                "words": [
                    {"word": word.word, "start": word.start, "end": word.end}
                    for word in (segment.words or [])
                ],
            }
        return

    result = model.transcribe(
        media_path,
        language="en",
        word_timestamps=True,
        condition_on_previous_text=True,
        hallucination_silence_threshold=2.0,
        verbose=False,
    )
    for segment in result.get("segments", []):
        yield {
            "text": segment.get("text", ""),
            "start": float(segment.get("start", 0.0)),
            "end": float(segment.get("end", 0.0)),
            "words": segment.get("words") or [],
        }
