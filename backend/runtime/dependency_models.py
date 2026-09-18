"""Immutable dependency inventory and approved-install contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .dependency_specs import YTDLP_VERSION, DENO_VERSION


DependencyState = Literal["ready", "missing", "invalid"]

InstallKind = Literal["command", "model_download"]


@dataclass(frozen=True)
class DependencyStatus:
    id: str
    name: str
    state: DependencyState
    required_version: str | None
    installed_version: str | None
    path: Path | None
    detail: str
    install_supported: bool

    @property
    def ready(self) -> bool:
        return self.state == "ready"


def _missing_ytdlp_status() -> DependencyStatus:
    return DependencyStatus("ytdlp", "yt-dlp", "missing", YTDLP_VERSION, None, None, "yt-dlp was not found", True)


def _missing_js_runtime_status() -> DependencyStatus:
    return DependencyStatus("js_runtime", "JavaScript runtime", "missing", DENO_VERSION, None, None, "A JavaScript runtime was not found", True)


@dataclass(frozen=True)
class DependencyInventory:
    ffmpeg: DependencyStatus
    ffprobe: DependencyStatus
    python: tuple[DependencyStatus, ...]
    whisper_model: DependencyStatus
    ytdlp: DependencyStatus = field(default_factory=_missing_ytdlp_status)
    # Only needed for some YouTube downloads; intentionally excluded from ready/missing so it never blocks local processing.
    js_runtime: DependencyStatus = field(default_factory=_missing_js_runtime_status)

    @property
    def ready(self) -> bool:
        return all(
            status.ready
            for status in (self.ffmpeg, self.ffprobe, *self.python, self.ytdlp, self.whisper_model)
        )

    @property
    def missing(self) -> tuple[DependencyStatus, ...]:
        return tuple(
            status
            for status in (self.ffmpeg, self.ffprobe, *self.python, self.ytdlp, self.whisper_model)
            if not status.ready
        )


@dataclass(frozen=True)
class InstallAction:
    id: str
    dependency_ids: tuple[str, ...]
    kind: InstallKind
    description: str
    source_name: str
    source_url: str
    command: tuple[str, ...]
    estimated_download_bytes: int | None = None
    progress_path: Path | None = None
    component: str = ""
    version: str = ""
    purpose: str = ""
    license: str = ""
    requires_network: bool = True
    destination: Path | None = None


@dataclass(frozen=True)
class InstallPlan:
    id: str
    actions: tuple[InstallAction, ...]
    whisper_library: str = "faster-whisper"
    whisper_model: str = "large-v3"


@dataclass(frozen=True)
class InstallProgress:
    action_id: str
    phase: Literal["starting", "running", "verifying", "completed", "cancelled"]
    message: str
    completed_bytes: int | None = None
    total_bytes: int | None = None


@dataclass(frozen=True)
class InstallResult:
    action_id: str
    dependency_ids: tuple[str, ...]
    detail: str
