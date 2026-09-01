"""Canonical application identity and per-user storage paths."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path


DISPLAY_NAME = "Expletive Deleted"
APP_DATA_DIRECTORY_NAME = "ExpletiveDeleted"
DOCUMENTS_DIRECTORY_NAME = DISPLAY_NAME


def get_app_data_root(
    environment: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Return the canonical application-managed data root without creating it."""
    environment = os.environ if environment is None else environment
    local_app_data = environment.get("LOCALAPPDATA", "").strip()
    if not local_app_data:
        raise RuntimeError("LOCALAPPDATA is required to locate Expletive Deleted application data")
    return (Path(local_app_data).expanduser() / APP_DATA_DIRECTORY_NAME).resolve()


def get_documents_root(home: Path | None = None) -> Path:
    """Return the default root for user-owned media and transcripts."""
    if home is None:
        user_profile = os.environ.get("USERPROFILE", "").strip()
        home = Path(user_profile) if user_profile else Path.home()
    return (home.expanduser() / "Documents" / DOCUMENTS_DIRECTORY_NAME).resolve()


def prepare_app_data_root(
    environment: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Return the canonical application-managed data root without creating it."""
    return get_app_data_root(environment, home)