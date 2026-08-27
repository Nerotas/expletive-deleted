"""Resolve persisted settings with compatibility overrides."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

from backend.runtime.paths import RuntimePaths, get_runtime_paths

from .models import AppSettings, DirectorySettings
from .store import SettingsStore


def _directory_settings(paths: RuntimePaths) -> DirectorySettings:
    return DirectorySettings(
        input=paths.ready,
        output=paths.finished,
        archive=paths.processed,
        transcripts=paths.transcripts,
    )


def load_effective_settings(
    store: SettingsStore | None = None,
    *,
    legacy_root: Path | None = None,
) -> AppSettings:
    """Load settings, honoring an explicit or environment legacy workflow root."""
    settings = (store or SettingsStore()).load()
    configured_root = legacy_root or os.environ.get("CENSOR_PROJECT_ROOT")
    if configured_root:
        settings = replace(
            settings,
            directories=_directory_settings(get_runtime_paths(Path(configured_root))),
        )
    settings.validate()
    return settings


def resolve_runtime_paths(
    store: SettingsStore | None = None,
    *,
    legacy_root: Path | None = None,
) -> RuntimePaths:
    """Return processing paths from effective persisted settings."""
    return load_effective_settings(store, legacy_root=legacy_root).directories.to_runtime_paths()