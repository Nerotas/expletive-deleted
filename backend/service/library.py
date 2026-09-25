"""Read-only media library snapshots for the Queue interface."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from backend.censor import transcript_cache_is_compatible
from backend.jobs.media import MEDIA_EXTENSIONS, output_path, transcript_path, legacy_transcript_path, legacy_output_path
from backend.media_identity import read_record, valid_provenance, provenance_path
from backend.runtime import find_ffprobe
from backend.settings import AppSettings
from backend.filesystem.discovery import files_within


LibraryStatus = Literal["ready", "transcribed", "finished", "unverified"]


class LibraryScanError(RuntimeError):
    """Raised when the configured input directory cannot be scanned."""


@dataclass(frozen=True)
class LibraryItem:
    source: Path
    status: LibraryStatus
    date_added: datetime
    transcript: Path | None = None
    output: Path | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "source": str(self.source),
            "status": self.status,
            "date_added": self.date_added.isoformat(),
            "transcript": str(self.transcript) if self.transcript else None,
            "output": str(self.output) if self.output else None,
        }


@dataclass(frozen=True)
class ArchiveItem:
    """A user-visible original retained in the configured Processed folder."""

    source: Path
    relative_path: Path
    size_bytes: int
    archived_at: datetime

    def to_dict(self) -> dict[str, object]:
        return {
            "source": str(self.source),
            "relative_path": str(self.relative_path),
            "size_bytes": self.size_bytes,
            "archived_at": self.archived_at.isoformat(),
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
        candidates = files_within(settings.directories.binding(paths.ready), recursive=settings.source.scan_subdirectories)
        sources = sorted(
            (
                path
                for path in candidates
                if path.is_file() and not path.is_symlink() and ".downloads" not in path.relative_to(paths.ready).parts and path.suffix.lower() in MEDIA_EXTENSIONS
            ),
            key=lambda path: str(path.relative_to(paths.ready)).casefold(),
        )
    except OSError as exc:
        raise LibraryScanError(f"Could not scan input directory {paths.ready}: {exc}") from exc

    items: list[LibraryItem] = []
    for source in sources:
        date_added = datetime.fromtimestamp(source.stat().st_ctime, tz=timezone.utc)
        transcript = transcript_path(source, paths.transcripts, paths.ready)
        output = output_path(source, paths.finished, paths.ready)
        settings.directories.binding(paths.transcripts).target(transcript)
        settings.directories.binding(paths.finished).target(output)
        legacy_transcript = legacy_transcript_path(source, paths.transcripts, paths.ready)
        legacy_output = legacy_output_path(source, paths.finished, paths.ready)
        settings.directories.binding(paths.transcripts).target(legacy_transcript)
        settings.directories.binding(paths.finished).target(legacy_output)
        sidecar = provenance_path(output)
        settings.directories.binding(paths.finished).target(sidecar)
        try:
            metadata = read_record(sidecar) if sidecar.is_file() else {}
            # Polling reads recorded metadata only; equal size never proves matching contents.
            recorded_output = (valid_provenance(metadata)
                               and metadata["source_identity"]["size_bytes"] == source.stat().st_size)
        except (OSError, ValueError, RuntimeError):
            recorded_output = False
        if output.is_file() and recorded_output:
            items.append(
                LibraryItem(
                    source=source,
                    status="finished",
                    date_added=date_added,
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
            items.append(LibraryItem(source, "transcribed", date_added, transcript=transcript,
                                     output=output if output.is_file() else None))
        else:
            has_artifacts = any(path.exists() for path in (transcript, output, legacy_transcript, legacy_output))
            items.append(LibraryItem(source, "unverified" if has_artifacts else "ready", date_added))
    return tuple(items)


def scan_archive(settings: AppSettings) -> tuple[ArchiveItem, ...]:
    """Return supported originals retained in Processed, without following symlinks."""
    settings.validate()
    archive_root = settings.directories.archive
    if not archive_root.is_dir():
        raise LibraryScanError(f"Archive directory is not available: {archive_root}")
    try:
        items = [
            ArchiveItem(
                source=path,
                relative_path=path.relative_to(archive_root),
                size_bytes=path.stat().st_size,
                archived_at=datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc),
            )
            for path in files_within(settings.directories.binding(archive_root))
            if path.is_file() and not path.is_symlink() and path.suffix.lower() in MEDIA_EXTENSIONS
        ]
    except OSError as exc:
        raise LibraryScanError(f"Could not scan archive directory {archive_root}: {exc}") from exc
    return tuple(sorted(items, key=lambda item: str(item.relative_path).casefold()))
