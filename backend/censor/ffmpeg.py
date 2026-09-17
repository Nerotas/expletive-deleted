"""Cancellable FFmpeg execution and structured progress reporting."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from threading import Event
from typing import Callable


def _parse_ffmpeg_time(value: str) -> float:
    """Convert FFmpeg's HH:MM:SS.microseconds progress value to seconds."""
    try:
        hours, minutes, seconds = value.split(":")
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except (TypeError, ValueError):
        return 0.0



def format_seconds(seconds: float) -> str:
    """Render elapsed time consistently for model and FFmpeg progress."""
    whole = max(0, int(round(seconds)))
    hours, remainder = divmod(whole, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


class ProcessingCancelled(RuntimeError):
    """Raised when an active media job is cancelled."""



def run_ffmpeg_with_progress(
    command: list[str],
    duration: float | None,
    progress_callback: Callable[[dict[str, object]], None] | None = None,
    cancellation: Event | None = None,
) -> subprocess.CompletedProcess:
    """Run FFmpeg and render its machine-readable progress stream."""
    progress_command = command[:1] + [
        "-hide_banner", "-loglevel", "error", "-nostats",
        "-progress", "pipe:1",
    ] + command[1:]
    started = time.perf_counter()
    last_percent = -1
    rendered = False

    # Drain progress from stdout without allowing a full stderr pipe to stall FFmpeg.
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as error_file:
        process = subprocess.Popen(
            progress_command,
            stdout=subprocess.PIPE,
            stderr=error_file,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        progress_values: dict[str, str] = {}
        if process.stdout is not None:
            for line in process.stdout:
                if cancellation is not None and cancellation.is_set():
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    raise ProcessingCancelled("Media processing was cancelled")
                key, separator, value = line.strip().partition("=")
                if not separator:
                    continue
                progress_values[key] = value
                if key != "progress":
                    continue

                encoded_seconds = _parse_ffmpeg_time(progress_values.get("out_time", ""))
                if duration and duration > 0:
                    percent = min(100, int(encoded_seconds / duration * 100))
                else:
                    percent = 100 if value == "end" else 0
                if value == "end":
                    percent = 100
                if percent == last_percent and value != "end":
                    continue

                speed_text = progress_values.get("speed", "N/A").strip() or "N/A"
                try:
                    speed = float(speed_text.rstrip("x"))
                except ValueError:
                    speed = 0.0
                remaining = max(0.0, (duration or 0.0) - encoded_seconds)
                eta = format_seconds(remaining / speed) if speed > 0 else "--:--"
                elapsed = format_seconds(time.perf_counter() - started)
                filled = int(percent * 24 / 100)
                bar = "#" * filled + "-" * (24 - filled)
                status = (
                    f"\r[FFmpeg] [{bar}] {percent:3d}% | fps {progress_values.get('fps', 'N/A')} | "
                    f"speed {speed_text} | elapsed {elapsed} | eta {eta}"
                )
                sys.stdout.write(status)
                sys.stdout.flush()
                if progress_callback is not None:
                    progress_callback(
                        {
                            "percent": float(percent),
                            "eta_seconds": remaining / speed if speed > 0 else None,
                            "fps": float(progress_values["fps"])
                            if progress_values.get("fps", "").replace(".", "", 1).isdigit()
                            else None,
                            "message": f"FFmpeg speed {speed_text}",
                        }
                    )
                rendered = True
                last_percent = percent

        returncode = process.wait()
        error_file.seek(0)
        stderr = error_file.read()

    if rendered:
        sys.stdout.write("\n")
        sys.stdout.flush()
    return subprocess.CompletedProcess(progress_command, returncode, "", stderr)
