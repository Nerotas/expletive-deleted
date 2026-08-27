"""Validated settings models for the processing backend."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from backend.runtime.paths import RuntimePaths


ProcessingMode = Literal["report_only", "censor"]
ProcessingDevice = Literal["auto", "cpu", "cuda"]
StereoCensorMethod = Literal["drop_audio", "karaoke"]
SurroundOutput = Literal["preserve_5_1", "downmix_stereo"]
VideoMode = Literal["h264", "preserve_source"]
WhisperLibrary = Literal["faster-whisper", "openai-whisper"]
WhisperModel = Literal["tiny", "base", "small", "medium", "large-v3"]


class SettingsValidationError(ValueError):
    """Raised when application settings violate the persisted schema."""

    def __init__(self, issues: list[str] | tuple[str, ...]):
        self.issues = tuple(issues)
        super().__init__("Invalid settings: " + "; ".join(self.issues))


def default_user_data_root(home: Path | None = None) -> Path:
    """Return the default user-visible working directory root."""
    if home is None:
        user_profile = os.environ.get("USERPROFILE", "").strip()
        home = Path(user_profile) if user_profile else Path.home()
    return (home.expanduser() / "Documents" / "Profanity Censor").resolve()


@dataclass(frozen=True)
class DirectorySettings:
    input: Path
    output: Path
    archive: Path
    transcripts: Path

    @classmethod
    def defaults(cls, home: Path | None = None) -> DirectorySettings:
        root = default_user_data_root(home)
        return cls(
            input=root / "Ready",
            output=root / "Finished",
            archive=root / "Processed",
            transcripts=root / "Transcripts",
        )

    def validate(self) -> None:
        values = {
            "directories.input": self.input,
            "directories.output": self.output,
            "directories.archive": self.archive,
            "directories.transcripts": self.transcripts,
        }
        issues: list[str] = []
        valid_paths: dict[str, Path] = {}
        for name, path in values.items():
            if not isinstance(path, Path):
                issues.append(f"{name} must be a path")
            elif not path.is_absolute():
                issues.append(f"{name} must be an absolute path")
            else:
                valid_paths[name] = path

        normalized: dict[str, str] = {}
        for name, path in valid_paths.items():
            key = os.path.normcase(os.path.normpath(str(path)))
            if key in normalized:
                issues.append(f"{name} must differ from {normalized[key]}")
            else:
                normalized[key] = name

        if issues:
            raise SettingsValidationError(issues)

    def to_runtime_paths(self) -> RuntimePaths:
        self.validate()
        return RuntimePaths(
            root=self.input.parent,
            ready=self.input,
            finished=self.output,
            processed=self.archive,
            transcripts=self.transcripts,
        )


@dataclass(frozen=True)
class ProcessingSettings:
    mode: ProcessingMode = "censor"
    device: ProcessingDevice = "auto"


@dataclass(frozen=True)
class CensoringSettings:
    stereo_method: StereoCensorMethod = "drop_audio"
    padding_before_ms: int = 150
    padding_after_ms: int = 150


@dataclass(frozen=True)
class AudioSettings:
    surround_output: SurroundOutput = "preserve_5_1"


@dataclass(frozen=True)
class VideoSettings:
    mode: VideoMode = "h264"


@dataclass(frozen=True)
class WhisperSettings:
    library: WhisperLibrary = "faster-whisper"
    model: WhisperModel = "large-v3"


@dataclass(frozen=True)
class SourceSettings:
    archive_after_success: bool = False


@dataclass(frozen=True)
class RuntimeSettings:
    ffmpeg_path: Path | None = None
    ffprobe_path: Path | None = None
    whisper_cache: Path | None = None


@dataclass(frozen=True)
class AppSettings:
    directories: DirectorySettings = field(default_factory=DirectorySettings.defaults)
    processing: ProcessingSettings = field(default_factory=ProcessingSettings)
    censoring: CensoringSettings = field(default_factory=CensoringSettings)
    audio: AudioSettings = field(default_factory=AudioSettings)
    video: VideoSettings = field(default_factory=VideoSettings)
    whisper: WhisperSettings = field(default_factory=WhisperSettings)
    source: SourceSettings = field(default_factory=SourceSettings)
    runtime: RuntimeSettings = field(default_factory=RuntimeSettings)

    @classmethod
    def defaults(cls, home: Path | None = None) -> AppSettings:
        return cls(directories=DirectorySettings.defaults(home))

    def validate(self) -> None:
        issues: list[str] = []
        if not isinstance(self.directories, DirectorySettings):
            issues.append("directories must be a DirectorySettings object")
        else:
            try:
                self.directories.validate()
            except SettingsValidationError as exc:
                issues.extend(exc.issues)

        expected_groups = (
            ("processing", self.processing, ProcessingSettings),
            ("censoring", self.censoring, CensoringSettings),
            ("audio", self.audio, AudioSettings),
            ("video", self.video, VideoSettings),
            ("whisper", self.whisper, WhisperSettings),
            ("source", self.source, SourceSettings),
            ("runtime", self.runtime, RuntimeSettings),
        )
        invalid_groups = [name for name, value, expected in expected_groups if not isinstance(value, expected)]
        issues.extend(f"{name} has an invalid settings object" for name in invalid_groups)
        if invalid_groups:
            raise SettingsValidationError(issues)

        allowed_values = (
            ("processing.mode", self.processing.mode, {"report_only", "censor"}),
            ("processing.device", self.processing.device, {"auto", "cpu", "cuda"}),
            ("censoring.stereo_method", self.censoring.stereo_method, {"drop_audio", "karaoke"}),
            ("audio.surround_output", self.audio.surround_output, {"preserve_5_1", "downmix_stereo"}),
            ("video.mode", self.video.mode, {"h264", "preserve_source"}),
            ("whisper.library", self.whisper.library, {"faster-whisper", "openai-whisper"}),
            ("whisper.model", self.whisper.model, {"tiny", "base", "small", "medium", "large-v3"}),
        )
        for name, value, allowed in allowed_values:
            if value not in allowed:
                issues.append(f"{name} must be one of: {', '.join(sorted(allowed))}")

        for name, value in (
            ("censoring.padding_before_ms", self.censoring.padding_before_ms),
            ("censoring.padding_after_ms", self.censoring.padding_after_ms),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10_000:
                issues.append(f"{name} must be an integer from 0 through 10000")

        if not isinstance(self.source.archive_after_success, bool):
            issues.append("source.archive_after_success must be a boolean")

        for name, value in (
            ("runtime.ffmpeg_path", self.runtime.ffmpeg_path),
            ("runtime.ffprobe_path", self.runtime.ffprobe_path),
            ("runtime.whisper_cache", self.runtime.whisper_cache),
        ):
            if value is not None and not isinstance(value, Path):
                issues.append(f"{name} must be a path or null")
            elif isinstance(value, Path) and not value.is_absolute():
                issues.append(f"{name} must be an absolute path")

        if issues:
            raise SettingsValidationError(issues)
