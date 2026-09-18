"""Whisper CPU/CUDA profile selection and optional device discovery."""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
from dataclasses import dataclass
from .locations import (
    REQUIRED_WHISPER_MODEL,
    read_project_config,
    require_whisper_model,
)


# First-run setup must import with only private Python's standard library present.
# Probe the optional native package only when device capabilities are requested.
ctranslate2 = None


@dataclass(frozen=True)
class WhisperDeviceStatus:
    requested: str
    selected: str
    compute_type: str
    detail: str


def get_cuda_memory_mib() -> int | None:
    """Return total memory for the first NVIDIA GPU when nvidia-smi is available."""
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return None
    result = subprocess.run(
        [nvidia_smi, "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        return int(result.stdout.splitlines()[0].strip())
    except ValueError:
        return None


def get_whisper_device_status(
    model_name: str = REQUIRED_WHISPER_MODEL,
    requested_device: str | None = None,
) -> WhisperDeviceStatus:
    """Select a safe CTranslate2 profile for the requested Whisper model."""
    model_name = require_whisper_model(model_name)
    parser = read_project_config()
    configured_device = parser.get("Whisper", "Device", fallback="auto").strip().lower()
    requested = os.environ.get(
        "CENSOR_WHISPER_DEVICE",
        requested_device or configured_device,
    ).strip().lower()
    requested = requested if requested in {"auto", "cpu", "cuda"} else "auto"
    configured_compute = parser.get("Whisper", "ComputeType", fallback="auto").strip().lower()
    requested_compute = os.environ.get("CENSOR_WHISPER_COMPUTE_TYPE", configured_compute).strip().lower()

    if requested == "cpu":
        return WhisperDeviceStatus("cpu", "cpu", "int8", "CPU was explicitly requested.")

    # A packaged bridge starts before optional packages are installed, so retry
    # this import after approved setup instead of caching the initial miss.
    global ctranslate2
    if ctranslate2 is None:
        try:
            ctranslate2 = importlib.import_module("ctranslate2")
        except ImportError:
            pass

    if ctranslate2 is not None:
        try:
            if ctranslate2.get_cuda_device_count() > 0:
                supported = ctranslate2.get_supported_compute_types("cuda", 0)
                candidates = ("float16", "int8_float16", "int8_float32", "int8", "float32")
                compute_type = requested_compute if requested_compute in supported else next(
                    (candidate for candidate in candidates if candidate in supported), None
                )
                if compute_type:
                    memory_mib = get_cuda_memory_mib()
                    minimum_memory = {
                        "tiny": 2048,
                        "base": 2048,
                        "small": 4096,
                        "medium": 6144,
                        "large-v3": 8192,
                    }.get(model_name, 8192)
                    if requested == "cuda" or memory_mib is None or memory_mib >= minimum_memory:
                        detail = f"CUDA selected with {compute_type}."
                        if memory_mib is not None:
                            detail = f"CUDA selected with {compute_type} on {memory_mib} MiB VRAM."
                        return WhisperDeviceStatus(requested, "cuda", compute_type, detail)
                    return WhisperDeviceStatus(
                        requested,
                        "cpu",
                        "int8",
                        (
                            f"CUDA GPU has {memory_mib} MiB VRAM; Whisper {model_name} needs at least "
                            f"{minimum_memory} MiB. Using CPU int8."
                        ),
                    )
        except Exception:
            pass

    detail = "CUDA is unavailable; using CPU int8."
    if requested == "cuda":
        detail = "CUDA was explicitly requested but is unavailable; using CPU int8."
    return WhisperDeviceStatus(requested, "cpu", "int8", detail)
