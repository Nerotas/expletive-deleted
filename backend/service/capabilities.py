"""Structured runtime capability reporting."""

from __future__ import annotations

import os

from backend.runtime import (
    available_encoders,
    get_managed_whisper_cache_dir,
    get_whisper_device_status,
    inspect_dependencies,
)
from backend.runtime.environment import get_managed_ytdlp_path
from backend.settings import AppSettings


def _app_runtime_status(inventory) -> tuple[str, str, str]:
    """Describe app-owned runtime health separately from user-selected assets."""
    bundled = os.environ.get("CENSOR_BUNDLED_RUNTIME") == "1"
    runtime_ready = all(
        status.ready for status in (inventory.ffmpeg, inventory.ffprobe, *inventory.python, inventory.ytdlp)
    )
    if runtime_ready:
        return (
            "ready",
            "bundled" if bundled else "development",
            "Application components are verified.",
        )

    missing = [status.name for status in (inventory.ffmpeg, inventory.ffprobe, *inventory.python, inventory.ytdlp) if not status.ready]
    detail = "Could not verify: " + ", ".join(missing) + "."
    if bundled:
        return (
            "invalid",
            "bundled",
            f"A component that came with Expletive Deleted could not be verified. {detail} Reinstall the app.",
        )
    return (
        "missing",
        "development",
        f"Development processing components are unavailable. {detail}",
    )


def get_capabilities(settings: AppSettings) -> dict[str, object]:
    settings.validate()
    cache_dir = settings.runtime.whisper_cache or get_managed_whisper_cache_dir()
    inventory = inspect_dependencies(
        cache_dir,
        ffmpeg_bin=settings.runtime.ffmpeg_path,
        ffprobe_bin=settings.runtime.ffprobe_path,
        whisper_library=settings.whisper.library,
        whisper_model=settings.whisper.model,
        ytdlp_bin=settings.runtime.ytdlp_path or get_managed_ytdlp_path(),
    )
    app_runtime, app_runtime_source, app_runtime_detail = _app_runtime_status(inventory)
    requested_cuda = get_whisper_device_status(settings.whisper.model, "cuda")
    selected = get_whisper_device_status(settings.whisper.model, settings.processing.device)
    encoders: list[str] = []
    if inventory.ffmpeg.ready and inventory.ffmpeg.path:
        encoders = sorted(available_encoders(str(inventory.ffmpeg.path)))
    h264_conversion = (
        "not_requested"
        if settings.video.mode != "h264"
        else "available" if encoders else "unavailable"
    )
    model_ready = inventory.whisper_model.ready
    return {
        # Legacy fields remain until all renderer consumers use the grouped contract.
        "ready": app_runtime == "ready" and model_ready,
        "ffmpeg": inventory.ffmpeg.ready,
        "ffprobe": inventory.ffprobe.ready,
        "whisper": all(status.ready for status in inventory.python),
        "whisper_library": settings.whisper.library,
        "whisper_model": settings.whisper.model,
        "whisper_model_ready": model_ready,
        "model_large_v3": model_ready and settings.whisper.model == "large-v3",
        # Grouped system-check contract.
        "processing_ready": app_runtime == "ready" and model_ready,
        "app_runtime": app_runtime,
        "app_runtime_source": app_runtime_source,
        "app_runtime_detail": app_runtime_detail,
        "speech_model": "ready" if model_ready else inventory.whisper_model.state,
        "speech_model_name": settings.whisper.model,
        "speech_model_detail": inventory.whisper_model.detail,
        "h264_conversion": h264_conversion,
        "ffmpeg_version": inventory.ffmpeg.installed_version,
        "ffmpeg_path": str(inventory.ffmpeg.path) if inventory.ffmpeg.path else None,
        "ffprobe_path": str(inventory.ffprobe.path) if inventory.ffprobe.path else None,
        "model_path": str(inventory.whisper_model.path) if inventory.whisper_model.path else None,
        "whisper_device": selected.selected,
        "whisper_compute_type": selected.compute_type,
        "cuda": requested_cuda.selected == "cuda",
        "video_encoders": encoders,
        "ytdlp": inventory.ytdlp.ready,
        "ytdlp_version": inventory.ytdlp.installed_version,
        "ytdlp_path": str(inventory.ytdlp.path) if inventory.ytdlp.path else None,
        "ytdlp_detail": inventory.ytdlp.detail,
        # Only needed for some YouTube downloads; deliberately not part of app_runtime/processing_ready.
        "js_runtime": inventory.js_runtime.ready,
        "js_runtime_version": inventory.js_runtime.installed_version,
        "js_runtime_path": str(inventory.js_runtime.path) if inventory.js_runtime.path else None,
        "js_runtime_detail": inventory.js_runtime.detail,
    }
