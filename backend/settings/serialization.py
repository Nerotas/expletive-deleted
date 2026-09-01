"""JSON serialization for versioned application settings."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from .models import (
    AppSettings,
    AudioSettings,
    CensoringSettings,
    DirectorySettings,
    OnboardingSettings,
    ProcessingDevice,
    ProcessingMode,
    ProcessingSettings,
    RuntimeSettings,
    SettingsValidationError,
    SourceSettings,
    StereoCensorMethod,
    SurroundOutput,
    VideoMode,
    VideoSettings,
    WhisperLibrary,
    WhisperModel,
    WhisperSettings,
)


SETTINGS_SCHEMA_VERSION = 1
_TOP_LEVEL_KEYS = {
    "schema_version",
    "directories",
    "processing",
    "censoring",
    "audio",
    "video",
    "whisper",
    "source",
    "runtime",
    "onboarding",
}


def _mapping(value: object, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SettingsValidationError([f"{field_name} must be an object"])
    return value


def _group(
    data: Mapping[str, Any],
    name: str,
    allowed_keys: set[str],
) -> Mapping[str, Any]:
    value = _mapping(data.get(name, {}), name)
    unknown = sorted(set(value) - allowed_keys)
    if unknown:
        raise SettingsValidationError([f"{name} contains unknown field(s): {', '.join(unknown)}"])
    return value


def _string(group: Mapping[str, Any], name: str, default: str, field_name: str) -> str:
    value = group.get(name, default)
    if not isinstance(value, str) or not value.strip():
        raise SettingsValidationError([f"{field_name} must be a non-empty string"])
    return value.strip()


def _integer(group: Mapping[str, Any], name: str, default: int, field_name: str) -> int:
    value = group.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise SettingsValidationError([f"{field_name} must be an integer"])
    return value


def _boolean(group: Mapping[str, Any], name: str, default: bool, field_name: str) -> bool:
    value = group.get(name, default)
    if not isinstance(value, bool):
        raise SettingsValidationError([f"{field_name} must be a boolean"])
    return value


def _optional_path(group: Mapping[str, Any], name: str, default: Path | None, field_name: str) -> Path | None:
    value = group.get(name, str(default) if default is not None else None)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise SettingsValidationError([f"{field_name} must be an absolute path or null"])
    return Path(value.strip())


def settings_from_dict(data: object, defaults: AppSettings | None = None) -> AppSettings:
    """Parse and validate settings loaded from JSON-compatible data."""
    mapping = _mapping(data, "settings")
    unknown = sorted(set(mapping) - _TOP_LEVEL_KEYS)
    if unknown:
        raise SettingsValidationError([f"settings contains unknown field(s): {', '.join(unknown)}"])

    version = mapping.get("schema_version", SETTINGS_SCHEMA_VERSION)
    if isinstance(version, bool) or not isinstance(version, int):
        raise SettingsValidationError(["schema_version must be an integer"])
    if version != SETTINGS_SCHEMA_VERSION:
        raise SettingsValidationError(
            [f"schema_version {version} is unsupported; expected {SETTINGS_SCHEMA_VERSION}"]
        )

    base = defaults or AppSettings.defaults()
    directories = _group(mapping, "directories", {"input", "output", "archive", "transcripts"})
    processing = _group(mapping, "processing", {"mode", "device"})
    censoring = _group(
        mapping,
        "censoring",
        {"stereo_method", "padding_before_ms", "padding_after_ms"},
    )
    audio = _group(mapping, "audio", {"surround_output"})
    video = _group(mapping, "video", {"mode"})
    whisper = _group(mapping, "whisper", {"library", "model"})
    source = _group(mapping, "source", {"archive_after_success", "scan_subdirectories"})
    runtime = _group(mapping, "runtime", {"ffmpeg_path", "ffprobe_path", "whisper_cache"})
    onboarding = _group(mapping, "onboarding", {"completed"})

    parsed = AppSettings(
        directories=DirectorySettings(
            input=Path(_string(directories, "input", str(base.directories.input), "directories.input")),
            output=Path(_string(directories, "output", str(base.directories.output), "directories.output")),
            archive=Path(_string(directories, "archive", str(base.directories.archive), "directories.archive")),
            transcripts=Path(
                _string(
                    directories,
                    "transcripts",
                    str(base.directories.transcripts),
                    "directories.transcripts",
                )
            ),
        ),
        processing=ProcessingSettings(
            mode=cast(
                ProcessingMode,
                _string(processing, "mode", base.processing.mode, "processing.mode"),
            ),
            device=cast(
                ProcessingDevice,
                _string(processing, "device", base.processing.device, "processing.device"),
            ),
        ),
        censoring=CensoringSettings(
            stereo_method=cast(
                StereoCensorMethod,
                _string(
                    censoring,
                    "stereo_method",
                    base.censoring.stereo_method,
                    "censoring.stereo_method",
                ),
            ),
            padding_before_ms=_integer(
                censoring,
                "padding_before_ms",
                base.censoring.padding_before_ms,
                "censoring.padding_before_ms",
            ),
            padding_after_ms=_integer(
                censoring,
                "padding_after_ms",
                base.censoring.padding_after_ms,
                "censoring.padding_after_ms",
            ),
        ),
        audio=AudioSettings(
            surround_output=cast(
                SurroundOutput,
                _string(
                    audio,
                    "surround_output",
                    base.audio.surround_output,
                    "audio.surround_output",
                ),
            )
        ),
        video=VideoSettings(
            mode=cast(
                VideoMode,
                _string(video, "mode", base.video.mode, "video.mode"),
            )
        ),
        whisper=WhisperSettings(
            library=cast(
                WhisperLibrary,
                _string(whisper, "library", base.whisper.library, "whisper.library"),
            ),
            model=cast(
                WhisperModel,
                _string(whisper, "model", base.whisper.model, "whisper.model"),
            )
        ),
        source=SourceSettings(
            archive_after_success=_boolean(
                source,
                "archive_after_success",
                base.source.archive_after_success,
                "source.archive_after_success",
            ),
            scan_subdirectories=_boolean(
                source,
                "scan_subdirectories",
                base.source.scan_subdirectories,
                "source.scan_subdirectories",
            ),
        ),
        runtime=RuntimeSettings(
            ffmpeg_path=_optional_path(
                runtime,
                "ffmpeg_path",
                base.runtime.ffmpeg_path,
                "runtime.ffmpeg_path",
            ),
            ffprobe_path=_optional_path(
                runtime,
                "ffprobe_path",
                base.runtime.ffprobe_path,
                "runtime.ffprobe_path",
            ),
            whisper_cache=_optional_path(
                runtime,
                "whisper_cache",
                base.runtime.whisper_cache,
                "runtime.whisper_cache",
            ),
        ),
        onboarding=OnboardingSettings(
            completed=_boolean(
                onboarding,
                "completed",
                base.onboarding.completed,
                "onboarding.completed",
            )
        ),
    )
    parsed.validate()
    return parsed


def settings_to_dict(settings: AppSettings) -> dict[str, object]:
    """Return the complete JSON-compatible representation of settings."""
    settings.validate()
    return {
        "schema_version": SETTINGS_SCHEMA_VERSION,
        "directories": {
            "input": str(settings.directories.input),
            "output": str(settings.directories.output),
            "archive": str(settings.directories.archive),
            "transcripts": str(settings.directories.transcripts),
        },
        "processing": {
            "mode": settings.processing.mode,
            "device": settings.processing.device,
        },
        "censoring": {
            "stereo_method": settings.censoring.stereo_method,
            "padding_before_ms": settings.censoring.padding_before_ms,
            "padding_after_ms": settings.censoring.padding_after_ms,
        },
        "audio": {"surround_output": settings.audio.surround_output},
        "video": {"mode": settings.video.mode},
        "whisper": {"library": settings.whisper.library, "model": settings.whisper.model},
        "source": {
            "archive_after_success": settings.source.archive_after_success,
            "scan_subdirectories": settings.source.scan_subdirectories,
        },
        "runtime": {
            "ffmpeg_path": str(settings.runtime.ffmpeg_path) if settings.runtime.ffmpeg_path else None,
            "ffprobe_path": str(settings.runtime.ffprobe_path) if settings.runtime.ffprobe_path else None,
            "whisper_cache": str(settings.runtime.whisper_cache) if settings.runtime.whisper_cache else None,
        },
        "onboarding": {"completed": settings.onboarding.completed},
    }
