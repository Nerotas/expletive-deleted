"""Filesystem paths used by the processing backend."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class RuntimePaths:
    """Project folders used by the processing workflow."""

    root: Path
    ready: Path
    finished: Path
    processed: Path
    transcripts: Path

    @property
    def transcoded(self) -> Path:
        """Return the output directory using the legacy field name."""
        return self.finished

    def create(self) -> None:
        for path in (self.ready, self.finished, self.processed, self.transcripts):
            path.mkdir(parents=True, exist_ok=True)


def get_project_root(root: Path | None = None) -> Path:
    return Path(root or os.environ.get("CENSOR_PROJECT_ROOT", PROJECT_ROOT)).resolve()


def get_runtime_paths(root: Path | None = None) -> RuntimePaths:
    """Return project-relative paths, allowing the project root to be overridden."""
    project_root = get_project_root(root)
    return RuntimePaths(
        root=project_root,
        ready=project_root / "ready",
        finished=project_root / "finished",
        processed=project_root / "processed",
        transcripts=project_root / "transcripts",
    )