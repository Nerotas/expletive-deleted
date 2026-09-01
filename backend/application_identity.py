"""Canonical application identity and per-user storage paths."""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path


DISPLAY_NAME = "Expletive Deleted"
APP_DATA_DIRECTORY_NAME = "ExpletiveDeleted"
DOCUMENTS_DIRECTORY_NAME = DISPLAY_NAME
PACKAGE_SLUG = "expletive-deleted"
LEGACY_APP_DATA_DIRECTORY_NAMES = ("Profanity Censor", "ProfanityCensor")

_DURABLE_FILES = ("settings.ini", "settings.json", "policy.json", "ffmpeg-runtime.json")
_DURABLE_DIRECTORIES = ("settings", "dictionary", "dependencies", "models", "logs")


class AppDataMigrationError(RuntimeError):
    """Raised when legacy application data cannot be copied safely."""


def get_app_data_root(
    environment: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Return the canonical application-managed data root without creating it."""
    environment = os.environ if environment is None else environment
    configured = environment.get("CENSOR_APP_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()

    local_app_data = environment.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        return (Path(local_app_data).expanduser() / APP_DATA_DIRECTORY_NAME).resolve()

    home = (home or Path.home()).expanduser()
    data_home = environment.get("XDG_DATA_HOME", "").strip()
    base = Path(data_home).expanduser() if data_home else home / ".local" / "share"
    return (base / PACKAGE_SLUG).resolve()


def get_documents_root(home: Path | None = None) -> Path:
    """Return the default root for user-owned media and transcripts."""
    if home is None:
        user_profile = os.environ.get("USERPROFILE", "").strip()
        home = Path(user_profile) if user_profile else Path.home()
    return (home.expanduser() / "Documents" / DOCUMENTS_DIRECTORY_NAME).resolve()


def get_legacy_app_data_roots(
    environment: Mapping[str, str] | None = None,
) -> tuple[Path, ...]:
    """Return legacy Windows application-data roots in migration priority order."""
    environment = os.environ if environment is None else environment
    local_app_data = environment.get("LOCALAPPDATA", "").strip()
    if not local_app_data:
        return ()
    base = Path(local_app_data).expanduser()
    return tuple((base / name).resolve() for name in LEGACY_APP_DATA_DIRECTORY_NAMES)


def prepare_app_data_root(
    environment: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Migrate known durable legacy state when the canonical root is absent."""
    root = get_app_data_root(environment, home)
    effective_environment = os.environ if environment is None else environment
    if root.exists() or effective_environment.get("CENSOR_APP_DATA_DIR", "").strip():
        return root

    legacy_root = next((path for path in get_legacy_app_data_roots(environment) if path.is_dir()), None)
    if legacy_root is None:
        return root

    root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{APP_DATA_DIRECTORY_NAME}.migration-", dir=root.parent))
    try:
        copied = False
        for name in _DURABLE_FILES:
            source = legacy_root / name
            if source.is_file() and not source.name.endswith(".tmp"):
                shutil.copy2(source, staging / name)
                copied = True
        for name in _DURABLE_DIRECTORIES:
            source = legacy_root / name
            if source.is_dir():
                shutil.copytree(
                    source,
                    staging / name,
                    ignore=shutil.ignore_patterns("*.tmp", "__pycache__", "*.pyc"),
                )
                copied = True
        if copied:
            os.replace(staging, root)
        else:
            staging.rmdir()
    except OSError as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise AppDataMigrationError(
            f"Could not migrate application data from {legacy_root} to {root}: {exc}"
        ) from exc
    return root