"""Shared media discovery and artifact naming rules."""

from pathlib import Path


MEDIA_EXTENSIONS = {
    ".avi", ".flv", ".m4a", ".mkv", ".mov", ".mp3", ".mp4", ".wav", ".webm", ".wmv",
}
AUDIO_EXTENSIONS = {".m4a", ".mp3", ".wav"}


def relative_media_path(input_file: Path, input_root: Path | None = None) -> Path:
    """Return a safe source-relative path, or just the filename for legacy callers."""
    if input_root is None:
        return Path(input_file.name)
    try:
        return input_file.resolve().relative_to(input_root.resolve())
    except ValueError as exc:
        raise ValueError(f"Media source is outside the configured input directory: {input_file}") from exc


def output_path(input_file: Path, output_dir: Path, input_root: Path | None = None) -> Path:
    extension = ".mp3" if input_file.suffix.lower() in AUDIO_EXTENSIONS else ".mkv"
    relative = relative_media_path(input_file, input_root)
    return output_dir / relative.parent / f"{input_file.stem}-censored{extension}"


def transcript_path(input_file: Path, transcript_dir: Path, input_root: Path | None = None) -> Path:
    relative = relative_media_path(input_file, input_root)
    return transcript_dir / relative.parent / f"{input_file.name}-transcript.json"


def legacy_transcript_path(input_file: Path, transcript_dir: Path, input_root: Path | None = None) -> Path:
    relative = relative_media_path(input_file, input_root)
    return transcript_dir / relative.parent / f"{input_file.stem}-transcript.json"


def legacy_output_path(input_file: Path, output_dir: Path, input_root: Path | None = None) -> Path:
    """Return the previous full-source-filename output path for compatibility."""
    extension = ".mp3" if input_file.suffix.lower() in AUDIO_EXTENSIONS else ".mkv"
    relative = relative_media_path(input_file, input_root)
    return output_dir / relative.parent / f"{input_file.name}-censored{extension}"


def output_paths(input_file: Path, output_dir: Path, input_root: Path | None = None) -> tuple[Path, Path]:
    """Return the canonical output followed by the previously supported name."""
    return (
        output_path(input_file, output_dir, input_root),
        legacy_output_path(input_file, output_dir, input_root),
    )


def conflicting_output_source(
    input_file: Path,
    output_dir: Path,
    input_root: Path,
) -> Path | None:
    """Find a sibling media file that would map to the same container-free name."""
    destination = output_path(input_file, output_dir, input_root)
    for candidate in input_file.parent.iterdir():
        if candidate == input_file or candidate.is_symlink():
            continue
        if candidate.is_file() and candidate.suffix.lower() in MEDIA_EXTENSIONS:
            if output_path(candidate, output_dir, input_root) == destination:
                return candidate
    return None


def archive_path(input_file: Path, archive_dir: Path, input_root: Path) -> Path:
    return archive_dir / relative_media_path(input_file, input_root)
