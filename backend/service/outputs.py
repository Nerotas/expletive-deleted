"""Resolve and verify playback targets without trusting a renderer destination."""

from __future__ import annotations

import json
import subprocess
from contextlib import ExitStack
from pathlib import Path

from backend.filesystem.operations import locked_file
from backend.filesystem.paths import PathSafetyError, reject_alias, validate_path
from backend.jobs.media import MEDIA_EXTENSIONS, archive_path, output_path
from backend.runtime import find_ffprobe


class OutputAccessError(RuntimeError):
    code = "output_unavailable"


def verify_playback(path: Path, ffprobe: str | None):
    if not ffprobe:
        raise OutputAccessError("Install or locate FFprobe in Settings before playing verified output.")
    try:
        # Media metadata must not cause FFprobe to fetch a remote playlist or stream.
        result = subprocess.run(
            [ffprobe, '-v', 'error', '-protocol_whitelist', 'file,pipe',
             '-show_entries', 'stream=codec_type', '-of', 'json', str(path)],
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=15,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        streams = {item.get('codec_type') for item in json.loads(result.stdout)['streams']}
        if result.returncode or 'audio' not in streams or (path.suffix.lower() == '.mkv' and 'video' not in streams):
            raise ValueError('Missing readable media streams')
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise OutputAccessError("This output could not be verified. Check FFprobe in Settings or recreate the censored copy.") from exc


def prepare_output(service, source: str, resources: ExitStack):
    if not isinstance(source, str) or not source.strip():
        raise OutputAccessError('Choose a completed item in the Queue to play its output.')
    settings, jobs = service.output_context()
    directories = settings.directories
    selected = validate_path(Path(source))
    directories.binding(directories.input).target(selected)
    if selected.suffix.lower() not in MEDIA_EXTENSIONS or selected.is_symlink():
        raise OutputAccessError('Only supported Queue media can be played.')
    # Completed jobs retain the source name after optional archiving removes it from Ready.
    known_job = any(job.source == selected and job.mode == 'censor' and
                    (job.status == 'completed' or (job.error and job.error.code == 'archive_failed')) for job in jobs)
    if not selected.is_file() and not known_job:
        raise OutputAccessError('This Queue source is no longer available. Open moved files through Explorer.')
    original = selected if selected.is_file() else archive_path(selected, directories.archive, directories.input)
    if original.exists():
        source_root = directories.input if original == selected else directories.archive
        resources.enter_context(locked_file(directories.binding(source_root), original))
    destination = output_path(selected, directories.output, directories.input)
    root = directories.binding(directories.output)
    resources.enter_context(locked_file(root, destination))
    canonical = root.target(destination)
    if original.exists():
        reject_alias(original, canonical)
    if canonical.suffix.lower() not in {'.mp3', '.mkv'} or canonical.stat().st_size == 0:
        raise OutputAccessError('The censored output is empty or unsupported. Recreate it before playing.')
    verify_playback(canonical, str(settings.runtime.ffprobe_path) if settings.runtime.ffprobe_path else find_ffprobe())
    # Keep the root/file lease until Electron finishes handing this exact name to the OS.
    def check():
        if service.settings.directories != directories:
            raise PathSafetyError('Media folders changed. Select the Queue item again.')
        root.target(destination)
    check()
    return canonical, check
