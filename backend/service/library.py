"""Read-only media library snapshots for the Queue interface."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from backend.censor import transcript_cache_is_compatible
from backend.jobs.media import MEDIA_EXTENSIONS, output_path, transcript_path
from backend.runtime import find_ffprobe
from backend.settings import AppSettings


LibraryStatus = Literal["ready", "transcribed", "finished"]


class LibraryScanError(RuntimeError):
    """Raised when the configured input directory cannot be scanned."""


@dataclass(frozen=True)
class LibraryItem:
    source: Path
    status: LibraryStatus
    transcript: Path | None = None
    output: Path | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "source": str(self.source),
            "status": self.status,
            "transcript": str(self.transcript) if self.transcript else None,
            "output": str(self.output) if self.output else None,
        }


def scan_library(
    settings: AppSettings,
    *,
    ffprobe_bin: str | None = None,
) -> tuple[LibraryItem, ...]:
    """Return the current artifact-derived state of supported input media."""
    settings.validate()
    paths = settings.directories.to_runtime_paths()
    if not paths.ready.is_dir():
        raise LibraryScanError(f"Input directory is not available: {paths.ready}")

    ffprobe_bin = ffprobe_bin or find_ffprobe()
    try:
        candidates = paths.ready.rglob("*") if settings.source.scan_subdirectories else paths.ready.iterdir()
        sources = sorted(
            (
                path
                for path in candidates
                if path.is_file() and not path.is_symlink() and path.suffix.lower() in MEDIA_EXTENSIONS
            ),
            key=lambda path: str(path.relative_to(paths.ready)).casefold(),
        )
    except OSError as exc:
        raise LibraryScanError(f"Could not scan input directory {paths.ready}: {exc}") from exc

    items: list[LibraryItem] = []
    for source in sources:
        transcript = transcript_path(source, paths.transcripts, paths.ready)
        output = output_path(source, paths.finished, paths.ready)
        if output.is_file():
            items.append(
                LibraryItem(
                    source=source,
                    status="finished",
                    transcript=transcript if transcript.is_file() else None,
                    output=output,
                )
            )
        elif ffprobe_bin and transcript_cache_is_compatible(
            str(source),
            str(transcript),
            ffprobe_bin,
            settings.whisper.library,
            settings.whisper.model,
        ):
            items.append(LibraryItem(source, "transcribed", transcript=transcript))
        else:
            items.append(LibraryItem(source, "ready"))
    return tuple(items)
