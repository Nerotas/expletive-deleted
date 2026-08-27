"""Structured runtime capability reporting."""

from __future__ import annotations

from backend.runtime import (
    available_encoders,
    get_whisper_cache_dir,
    get_whisper_device_status,
    inspect_dependencies,
)
from backend.settings import AppSettings


def get_capabilities(settings: AppSettings) -> dict[str, object]:
    settings.validate()
    cache_dir = settings.runtime.whisper_cache or get_whisper_cache_dir()
    inventory = inspect_dependencies(
        cache_dir,
        ffmpeg_bin=settings.runtime.ffmpeg_path,
        ffprobe_bin=settings.runtime.ffprobe_path,
        whisper_library=settings.whisper.library,
        whisper_model=settings.whisper.model,
    )
    requested_cuda = get_whisper_device_status(settings.whisper.model, "cuda")
    selected = get_whisper_device_status(settings.whisper.model, settings.processing.device)
    encoders: list[str] = []
    if inventory.ffmpeg.ready and inventory.ffmpeg.path:
        encoders = sorted(available_encoders(str(inventory.ffmpeg.path)))
    return {
        "ready": inventory.ready,
        "ffmpeg": inventory.ffmpeg.ready,
        "ffprobe": inventory.ffprobe.ready,
        "ffmpeg_version": inventory.ffmpeg.installed_version,
        "ffmpeg_path": str(inventory.ffmpeg.path) if inventory.ffmpeg.path else None,
        "ffprobe_path": str(inventory.ffprobe.path) if inventory.ffprobe.path else None,
        "whisper": all(status.ready for status in inventory.python),
        "whisper_library": settings.whisper.library,
        "whisper_model": settings.whisper.model,
        "whisper_model_ready": inventory.whisper_model.ready,
        "model_large_v3": inventory.whisper_model.ready and settings.whisper.model == "large-v3",
        "model_path": str(inventory.whisper_model.path) if inventory.whisper_model.path else None,
        "cuda": requested_cuda.selected == "cuda",
        "whisper_device": selected.selected,
        "whisper_compute_type": selected.compute_type,
        "video_encoders": encoders,
    }
