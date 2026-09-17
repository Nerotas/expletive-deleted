"""FFmpeg encoder discovery and hardware-availability checks."""

from __future__ import annotations

import subprocess
from functools import lru_cache
from typing import Iterable


ENCODER_PREFERENCE = (
    "h264_mf",
    "h264_nvenc",
    "h264_qsv",
    "h264_amf",
    "h264_videotoolbox",
    "libx264",
)


def available_encoders(ffmpeg_bin: str) -> set[str]:
    """Return video encoders reported by the installed FFmpeg binary."""
    result = subprocess.run(
        [ffmpeg_bin, "-hide_banner", "-encoders"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return set()

    encoders = set()
    for line in (result.stdout + result.stderr).splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[0].startswith("V") and fields[1] != "=":
            encoders.add(fields[1])
    return encoders


def select_video_encoder(
    encoders: Iterable[str], override: str | None = None
) -> str:
    """Choose a supported H.264 encoder, honoring an explicit override."""
    available = set(encoders)
    if override:
        if override not in available:
            raise ValueError(f"Requested video encoder is unavailable: {override}")
        return override

    for encoder in ENCODER_PREFERENCE:
        if encoder in available:
            return encoder
    raise RuntimeError("FFmpeg does not provide a supported H.264 encoder")


@lru_cache(maxsize=None)
def video_encoder_runtime_available(ffmpeg_bin: str, encoder: str) -> bool:
    """Return whether an encoder can produce a frame on the current machine."""
    try:
        result = subprocess.run(
            [
                ffmpeg_bin,
                "-v", "error",
                "-f", "lavfi",
                "-i", "testsrc2=size=128x128:rate=1",
                "-frames:v", "1",
                "-c:v", encoder,
                "-f", "null",
                "-",
            ],
            capture_output=True,
            timeout=15,
            check=False,
        )
        return result.returncode == 0
    except Exception:
        return False


def select_working_video_encoder(
    ffmpeg_bin: str,
    encoders: Iterable[str],
    override: str | None = None,
) -> str:
    """Choose the preferred encoder that is usable on the current machine."""
    available = set(encoders)
    if override:
        selected = select_video_encoder(available, override)
        if not video_encoder_runtime_available(ffmpeg_bin, selected):
            raise RuntimeError(f"Requested video encoder cannot run on this machine: {selected}")
        return selected

    for encoder in ENCODER_PREFERENCE:
        if encoder in available and video_encoder_runtime_available(ffmpeg_bin, encoder):
            return encoder
    raise RuntimeError("FFmpeg does not provide a working H.264 encoder")
