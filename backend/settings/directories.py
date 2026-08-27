"""Filesystem validation for configured user working directories."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .models import DirectorySettings


@dataclass(frozen=True)
class DirectoryStatus:
    field: str
    path: Path
    exists: bool
    is_directory: bool
    readable: bool
    writable: bool
    error: str | None = None

    @property
    def ready(self) -> bool:
        return self.exists and self.is_directory and self.readable and self.writable and self.error is None


class DirectoryAccessError(RuntimeError):
    """Raised when configured working directories are not usable."""

    def __init__(self, statuses: tuple[DirectoryStatus, ...]):
        self.statuses = statuses
        issues = [f"{status.field} ({status.path}): {status.error or 'not accessible'}" for status in statuses]
        super().__init__("Invalid working directories: " + "; ".join(issues))


def _configured_paths(settings: DirectorySettings) -> tuple[tuple[str, Path], ...]:
    return (
        ("directories.input", settings.input),
        ("directories.output", settings.output),
        ("directories.archive", settings.archive),
        ("directories.transcripts", settings.transcripts),
    )


def inspect_directories(
    settings: DirectorySettings,
    *,
    create: bool = False,
) -> tuple[DirectoryStatus, ...]:
    """Report whether each configured directory is ready for processing."""
    settings.validate()
    statuses: list[DirectoryStatus] = []
    for field_name, path in _configured_paths(settings):
        error: str | None = None
        if create:
            try:
                path.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                error = str(exc)

        exists = path.exists()
        is_directory = path.is_dir()
        readable = is_directory and os.access(path, os.R_OK)
        writable = is_directory and os.access(path, os.W_OK)
        if not exists:
            error = error or "directory does not exist"
        elif not is_directory:
            error = "path is not a directory"
        elif not readable:
            error = "directory is not readable"
        elif not writable:
            error = "directory is not writable"

        statuses.append(
            DirectoryStatus(
                field=field_name,
                path=path,
                exists=exists,
                is_directory=is_directory,
                readable=readable,
                writable=writable,
                error=error,
            )
        )
    return tuple(statuses)


def ensure_directories(settings: DirectorySettings) -> tuple[DirectoryStatus, ...]:
    """Create configured directories and raise when any remain unusable."""
    statuses = inspect_directories(settings, create=True)
    failures = tuple(status for status in statuses if not status.ready)
    if failures:
        raise DirectoryAccessError(failures)
    return statuses