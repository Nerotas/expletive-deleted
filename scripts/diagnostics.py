#!/usr/bin/env python3
"""Check whether the local CLI processing runtime is ready."""

from __future__ import annotations

import importlib.util
import shutil
from dataclasses import dataclass
from pathlib import Path

from backend.runtime import (
    available_encoders,
    find_ffmpeg,
    find_ffprobe,
    format_bytes,
    get_whisper_cache_dir,
    get_whisper_device_status,
    select_working_video_encoder,
)
from backend.settings import SettingsFileError, SettingsStore, inspect_directories, load_effective_settings


@dataclass(frozen=True)
class DiagnosticResult:
    name: str
    ok: bool
    detail: str
    required: bool = True


def _nearest_existing_path(path: Path) -> Path:
    candidate = path
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate


def collect_diagnostics(store: SettingsStore | None = None) -> list[DiagnosticResult]:
    results: list[DiagnosticResult] = []

    for import_name, display_name in (
        ("faster_whisper", "faster-whisper"),
        ("better_profanity", "better-profanity"),
        ("numpy", "NumPy"),
    ):
        available = importlib.util.find_spec(import_name) is not None
        detail = "installed" if available else "not installed"
        results.append(DiagnosticResult(display_name, available, detail))

    store = store or SettingsStore()
    try:
        settings = load_effective_settings(store)
        source = "persisted" if store.path.is_file() else "defaults"
        results.append(DiagnosticResult("Settings", True, f"{source}: {store.path}"))
        for status in inspect_directories(settings.directories):
            results.append(
                DiagnosticResult(
                    status.field,
                    status.ready,
                    str(status.path) if status.ready else f"{status.path}: {status.error}",
                )
            )
    except SettingsFileError as exc:
        settings = None
        results.append(DiagnosticResult("Settings", False, str(exc)))

    ffmpeg = find_ffmpeg()
    ffprobe = find_ffprobe()
    results.append(DiagnosticResult("FFmpeg", ffmpeg is not None, ffmpeg or "not found"))
    results.append(DiagnosticResult("FFprobe", ffprobe is not None, ffprobe or "not found"))

    if ffmpeg:
        try:
            encoder = select_working_video_encoder(ffmpeg, available_encoders(ffmpeg))
            results.append(DiagnosticResult("H.264 encoder", True, encoder))
        except (RuntimeError, ValueError) as exc:
            results.append(DiagnosticResult("H.264 encoder", False, str(exc)))

    try:
        requested_device = settings.processing.device if settings is not None else None
        status = get_whisper_device_status(requested_device=requested_device)
        results.append(
            DiagnosticResult(
                "Whisper device",
                True,
                f"{status.selected} ({status.compute_type}): {status.detail}",
            )
        )
    except Exception as exc:
        results.append(DiagnosticResult("Whisper device", False, str(exc)))

    cache_dir = get_whisper_cache_dir()
    results.append(
        DiagnosticResult(
            "Whisper cache",
            cache_dir.is_dir(),
            str(cache_dir),
            required=False,
        )
    )

    try:
        disk_path = (
            _nearest_existing_path(settings.directories.output)
            if settings is not None
            else Path.cwd()
        )
        free_bytes = shutil.disk_usage(disk_path).free
        minimum_free_bytes = 1024**3
        results.append(
            DiagnosticResult(
                "Free disk space",
                free_bytes >= minimum_free_bytes,
                format_bytes(free_bytes),
                required=False,
            )
        )
    except OSError as exc:
        results.append(DiagnosticResult("Free disk space", False, str(exc), required=False))

    return results


def main() -> int:
    print("Profanity Censor runtime diagnostics")
    print("=" * 36)

    results = collect_diagnostics()
    for result in results:
        label = "OK" if result.ok else ("FAIL" if result.required else "WARN")
        print(f"[{label}] {result.name}: {result.detail}")

    failures = [result for result in results if result.required and not result.ok]
    if failures:
        print(f"\nNot ready: {len(failures)} required check(s) failed.")
        return 1

    print("\nReady. Place media in the configured input directory and run: python batch_process.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())