"""Profanity transcription, detection, and media censoring."""

from .transcripts import (
    TranscriptValidationError,
    transcript_cache_is_compatible,
    validate_transcript_data,
    write_transcript_atomic,
)
from .detection import find_review_candidates
from .media import (
    has_discrete_center_channel,
    is_5_1_stream,
    is_7_1_stream,
    probe_audio_stream,
)
from .ffmpeg import run_ffmpeg_with_progress


def __getattr__(name: str):
    # Library scans need transcript checks, not the processing engine or model setup.
    if name == "ProfanityCensor":
        from .engine import ProfanityCensor

        return ProfanityCensor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "ProfanityCensor",
    "TranscriptValidationError",
    "find_review_candidates",
    "has_discrete_center_channel",
    "is_5_1_stream",
    "is_7_1_stream",
    "probe_audio_stream",
    "run_ffmpeg_with_progress",
    "transcript_cache_is_compatible",
    "validate_transcript_data",
    "write_transcript_atomic",
]
