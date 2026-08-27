"""Shared media discovery and artifact naming rules."""

from pathlib import Path


MEDIA_EXTENSIONS = {
    ".avi", ".flv", ".m4a", ".mkv", ".mov", ".mp3", ".mp4", ".wav", ".webm", ".wmv",
}
AUDIO_EXTENSIONS = {".m4a", ".mp3", ".wav"}


def output_path(input_file: Path, output_dir: Path) -> Path:
    extension = ".mp3" if input_file.suffix.lower() in AUDIO_EXTENSIONS else ".mkv"
    return output_dir / f"{input_file.stem}-censored{extension}"


def transcript_path(input_file: Path, transcript_dir: Path) -> Path:
    return transcript_dir / f"{input_file.stem}-transcript.json"