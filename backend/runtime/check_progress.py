"""Fixed-size, content-free component timing for local verification."""

from __future__ import annotations

import time
from typing import Any, Callable

STAGES = frozenset({"media_tools", "ffmpeg", "ffprobe", "python_packages", "speech_model",
                    "ytdlp", "js_runtime", "device", "encoders"})
Progress = Callable[[str, str, float], None]


def check_stage(progress: Progress | None, stage: str, operation: Callable[..., Any], *args, **kwargs) -> Any:
    started = time.monotonic()
    if progress:
        progress(stage, "started", 0)
    try:
        result = operation(*args, **kwargs)
    except Exception:
        if progress:
            progress(stage, "failed", (time.monotonic() - started) * 1000)
        raise
    if progress:
        progress(stage, "completed", (time.monotonic() - started) * 1000)
    return result
