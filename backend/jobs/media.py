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
    return transcript_dir / relative.parent / f"{input_file.stem}-transcript.json"


def archive_path(input_file: Path, archive_dir: Path, input_root: Path) -> Path:
    return archive_dir / relative_media_path(input_file, input_root)
