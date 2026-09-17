"""Transcript validation, atomic persistence, and source-channel compatibility."""

from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path
from typing import Dict

from .media import probe_audio_stream, has_discrete_center_channel


class TranscriptValidationError(RuntimeError):
    """Raised when a transcript cannot safely unlock downstream processing."""


def validate_transcript_data(
    transcript_data: object,
    *,
    whisper_library: str | None = None,
    whisper_model: str | None = None,
    require_front_center: bool = False,
) -> Dict:
    """Validate the persisted transcript contract used by detection and censoring."""
    if not isinstance(transcript_data, dict):
        raise TranscriptValidationError("Transcript must be a JSON object")
    if not isinstance(transcript_data.get("text"), str):
        raise TranscriptValidationError("Transcript text must be a string")

    words = transcript_data.get("words")
    if not isinstance(words, list):
        raise TranscriptValidationError("Transcript words must be a list")
    for index, item in enumerate(words):
        if not isinstance(item, dict) or not isinstance(item.get("word"), str):
            raise TranscriptValidationError(f"Transcript word {index} is invalid")
        start = item.get("start")
        end = item.get("end")
        if (
            isinstance(start, bool)
            or isinstance(end, bool)
            or not isinstance(start, (int, float))
            or not isinstance(end, (int, float))
            or not math.isfinite(float(start))
            or not math.isfinite(float(end))
            or start < 0
            or end < start
        ):
            raise TranscriptValidationError(
                f"Transcript word {index} has invalid timestamps"
            )

    audio_source = transcript_data.get("audio_source")
    if audio_source not in ("full_mix", "front_center"):
        raise TranscriptValidationError("Transcript audio source is invalid")
    if require_front_center and audio_source != "front_center":
        raise TranscriptValidationError(
            "Transcript must use the source's front-center audio channel"
        )
    if whisper_library and transcript_data.get("whisper_library") != whisper_library:
        raise TranscriptValidationError("Transcript uses a different Whisper library")
    if whisper_model and transcript_data.get("whisper_model") != whisper_model:
        raise TranscriptValidationError("Transcript uses a different Whisper model")
    return transcript_data


def write_transcript_atomic(
    transcript_path: Path,
    transcript_data: Dict,
    *,
    whisper_library: str,
    whisper_model: str,
    require_front_center: bool,
) -> Dict:
    """Atomically persist and verify a transcript before it can unlock transcoding."""
    validate = lambda value: validate_transcript_data(
        value,
        whisper_library=whisper_library,
        whisper_model=whisper_model,
        require_front_center=require_front_center,
    )
    validate(transcript_data)
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=transcript_path.parent,
            prefix=f".{transcript_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            json.dump(transcript_data, temporary_file, indent=2)
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)

        with temporary_path.open(encoding="utf-8") as source:
            validate(json.load(source))
        # Publish only the flushed, re-read transcript; interrupted writes stay private.
        os.replace(temporary_path, transcript_path)
        temporary_path = None
        with transcript_path.open(encoding="utf-8") as source:
            return validate(json.load(source))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise TranscriptValidationError(
            f"Transcript could not be saved and verified: {exc}"
        ) from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def transcript_cache_is_compatible(
    input_file: str,
    transcript_path: str,
    ffprobe_bin: str,
    whisper_library: str | None = None,
    whisper_model: str | None = None,
) -> bool:
    """Return whether a transcript exists and uses the right source channels."""
    if not os.path.exists(transcript_path):
        return False
    channels, layout = probe_audio_stream(ffprobe_bin, input_file)
    try:
        # Transcript writers always use UTF-8, regardless of the Windows code page.
        with open(transcript_path, 'r', encoding='utf-8') as transcript_file:
            transcript_data = json.load(transcript_file)
        validate_transcript_data(
            transcript_data,
            whisper_library=whisper_library,
            whisper_model=whisper_model,
            require_front_center=has_discrete_center_channel(channels, layout),
        )
        return True
    except Exception:
        return False
