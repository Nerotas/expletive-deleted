"""Transcript validation, atomic persistence, and source-channel compatibility."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Dict

from .media import probe_audio_stream, has_discrete_center_channel
from backend.filesystem.paths import RootBinding, version
from backend.filesystem.publication import Publication
from backend.media_identity import require_identity, valid_identity
from backend.filesystem.discovery import files_within
from backend.media_identity import read_record, MediaIdentityError


def find_matching_transcript(root: Path, source_identity: dict, *, whisper_library: str,
                             whisper_model: str, require_front_center: bool, cancellation=None) -> Dict | None:
    """Reuse a uniquely matching recorded transcript after a rename or relocation."""
    matches = []
    incompatible = False
    if not root.is_dir():
        return None
    for path in files_within(RootBinding.capture(root)):
        if cancellation is not None and cancellation.is_set():
            raise InterruptedError("Transcript lookup cancelled")
        if not path.name.endswith("-transcript.json"):
            continue
        try:
            data = read_record(path)
        except (OSError, ValueError, MediaIdentityError):
            continue
        # A current source hash cannot establish the origin of an unrecorded legacy transcript.
        if data.get("source_identity") != source_identity:
            continue
        try:
            validate_transcript_data(data, whisper_library=whisper_library, whisper_model=whisper_model,
                                     require_front_center=require_front_center, source_identity=source_identity)
        except TranscriptValidationError:
            incompatible = True
            continue
        # Identical copies are reusable; differing transcripts require an explicit choice.
        if data not in matches:
            matches.append(data)
    if len(matches) > 1:
        raise MediaIdentityError("Multiple different transcripts match this source. Existing files are preserved; "
                                 "review them before choosing one, or explicitly Retranscribe.")
    if matches:
        return matches[0]
    if incompatible:
        raise MediaIdentityError("A transcript matches this source but uses incompatible settings. "
                                 "Choose Retranscribe explicitly to create a compatible transcript.")
    return None


class TranscriptValidationError(RuntimeError):
    """Raised when a transcript cannot safely unlock downstream processing."""


def validate_transcript_data(
    transcript_data: object,
    *,
    whisper_library: str | None = None,
    whisper_model: str | None = None,
    require_front_center: bool = False,
    source_identity: dict | None = None,
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
    if source_identity is not None:
        require_identity(transcript_data, source_identity)
    return transcript_data


def write_transcript_atomic(
    transcript_path: Path,
    transcript_data: Dict,
    *,
    whisper_library: str,
    whisper_model: str,
    require_front_center: bool,
    source_identity: dict | None = None,
    cancellation=None,
) -> Dict:
    """Atomically persist and verify a transcript before it can unlock transcoding."""
    validate = lambda value: validate_transcript_data(
        value,
        whisper_library=whisper_library,
        whisper_model=whisper_model,
        require_front_center=require_front_center,
        source_identity=source_identity,
    )
    validate(transcript_data)
    try:
        root = RootBinding.capture(transcript_path.parent)
        selected_version = None
        # Keep the prior transcript even when the user explicitly requests a new one.
        # The content-addressed history file makes a repeated attempt idempotent.
        if transcript_path.exists():
            import hashlib
            from backend.filesystem.operations import locked_file
            with locked_file(root, transcript_path):
                selected_version = version(transcript_path)
                previous = transcript_path.read_bytes()
            history = transcript_path.parent / ".history" / (transcript_path.name + "." + hashlib.sha256(previous).hexdigest())
            root.target(history)
            if not history.exists():
                # History also preserves an empty/corrupt prior transcript exactly.
                with Publication(root, history, cancellation=cancellation, allow_empty=True) as backup:
                    backup.stage.write_bytes(previous)
                    def verify_history(path):
                        if path.read_bytes() != previous:
                            raise TranscriptValidationError("Transcript history verification failed")
                    backup.publish(verify_history)
            else:
                with locked_file(root, history):
                    if history.read_bytes() != previous:
                        raise TranscriptValidationError("Existing transcript history does not match; previous transcript retained")
        # Reject a concurrent replacement so the overwritten version is always the one preserved.
        with Publication(root, transcript_path, overwrite=selected_version is not None,
                         expected_version=selected_version, cancellation=cancellation) as publication:
            with publication.stage.open('w', encoding='utf-8') as temporary_file:
                json.dump(transcript_data, temporary_file, indent=2)
                temporary_file.write('\n')
            def verify(path):
                with path.open(encoding='utf-8') as source:
                    validate(json.load(source))
            publication.publish(verify)
        return transcript_data
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise TranscriptValidationError(
            f"Transcript could not be saved and verified: {exc}"
        ) from exc


def transcript_cache_is_compatible(
    input_file: str,
    transcript_path: str,
    ffprobe_bin: str,
    whisper_library: str | None = None,
    whisper_model: str | None = None,
    source_identity: dict | None = None,
) -> bool:
    """Check stored compatibility; only a supplied, freshly hashed identity proves content."""
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
            source_identity=source_identity,
        )
        return valid_identity(transcript_data.get("source_identity"))
    except Exception:
        return False
