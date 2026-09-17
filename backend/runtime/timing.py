"""Local transcription timing estimates, independent of processing orchestration."""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from backend.runtime.paths import get_project_root
from .devices import (
    get_whisper_device_status,
)
from .locations import (
    REQUIRED_WHISPER_MODEL,
    get_application_runtime_root,
)


WHISPER_TIMING_HISTORY_FILE = ".whisper-timing.json"


def get_whisper_timing_history_path(root: Path | None = None) -> Path:
    """Return the local, machine-specific transcription timing history file."""
    history_root = get_project_root(root) if root is not None else get_application_runtime_root()
    return history_root / WHISPER_TIMING_HISTORY_FILE


def get_whisper_profile_key(model_name: str = REQUIRED_WHISPER_MODEL) -> str:
    """Identify the selected model and execution profile for timing calibration."""
    status = get_whisper_device_status(model_name)
    return f"{model_name}:{status.selected}:{status.compute_type}"


def get_calibrated_transcription_factor(
    model_name: str = REQUIRED_WHISPER_MODEL, root: Path | None = None
) -> float | None:
    """Return the median recent wall-time/media-time factor for this profile."""
    history_path = get_whisper_timing_history_path(root)
    try:
        records = json.loads(history_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    profile_key = get_whisper_profile_key(model_name)
    factors = [
        record.get("seconds_per_media_second")
        for record in records
        if record.get("profile") == profile_key
        and isinstance(record.get("seconds_per_media_second"), (int, float))
        and record["seconds_per_media_second"] > 0
    ]
    return statistics.median(factors[-5:]) if factors else None


def record_transcription_timing(
    media_duration_seconds: float,
    elapsed_seconds: float,
    model_name: str = REQUIRED_WHISPER_MODEL,
    root: Path | None = None,
) -> None:
    """Persist one completed transcription measurement for future local estimates."""
    if media_duration_seconds <= 0 or elapsed_seconds <= 0:
        return

    history_path = get_whisper_timing_history_path(root)
    try:
        records = json.loads(history_path.read_text(encoding="utf-8"))
        if not isinstance(records, list):
            records = []
    except (OSError, json.JSONDecodeError):
        records = []

    records.append(
        {
            "profile": get_whisper_profile_key(model_name),
            "seconds_per_media_second": elapsed_seconds / media_duration_seconds,
        }
    )
    try:
        history_path.parent.mkdir(parents=True, exist_ok=True)
        history_path.write_text(json.dumps(records[-20:], indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass
