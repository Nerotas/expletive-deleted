#!/usr/bin/env python3
"""Check whether the local CLI processing runtime is ready."""

from __future__ import annotations

import importlib.util
import shutil
from dataclasses import dataclass

from backend.runtime import (
    available_encoders,
    find_ffmpeg,
    find_ffprobe,
    format_bytes,
    get_runtime_paths,
    get_whisper_cache_dir,
    get_whisper_device_status,
    select_working_video_encoder,
)


@dataclass(frozen=True)
class DiagnosticResult:
    name: str
    ok: bool
    detail: str
    required: bool = True


def collect_diagnostics() -> list[DiagnosticResult]:
    results: list[DiagnosticResult] = []

    for import_name, display_name in (
        ("faster_whisper", "faster-whisper"),
        ("better_profanity", "better-profanity"),
        ("numpy", "NumPy"),
    ):
        available = importlib.util.find_spec(import_name) is not None
        detail = "installed" if available else "not installed"
        results.append(DiagnosticResult(display_name, available, detail))

    paths = get_runtime_paths()
    try:
        paths.create()
        results.append(DiagnosticResult("Runtime folders", True, str(paths.root)))
    except OSError as exc:
        results.append(DiagnosticResult("Runtime folders", False, str(exc)))

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
        status = get_whisper_device_status()
        results.append(
            DiagnosticResult(
                "Whisper device",
                True,
                f"{status.selected} ({status.compute_type}): {status.detail}",
            )
        )
    except Exception as exc:
        results.append(DiagnosticResult("Whisper device", False, str(exc)))

    cache_dir = get_whisper_cache_dir(paths.root)
    results.append(
        DiagnosticResult(
            "Whisper cache",
            cache_dir.is_dir(),
            str(cache_dir),
            required=False,
        )
    )

    try:
        free_bytes = shutil.disk_usage(paths.root).free
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

    print("\nReady. Place media in ready/ and run: python batch_process.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())