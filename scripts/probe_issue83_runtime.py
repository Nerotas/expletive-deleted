"""Probe Issue 83 candidate wheels under an isolated target Python runtime.

Use synthetic media. This verifies execution, not artifact provenance, license
compliance, a clean-host install, or model transcription accuracy.
"""

from __future__ import annotations

import argparse
import importlib.metadata as metadata
import json
from pathlib import Path
import site
import sys
import time


def probe(site_packages: Path, video: Path, audio: Path, model: Path | None, require_no_cudnn: bool) -> dict:
    if not site_packages.is_dir() or not video.is_file() or not audio.is_file():
        raise ValueError("Existing site-packages, video, and audio paths are required")
    if require_no_cudnn and list(site_packages.rglob("cudnn*.dll")):
        raise ValueError("cuDNN DLL remains in the candidate Python payload")
    site.addsitedir(str(site_packages.resolve()))

    import av
    import ctranslate2
    import faster_whisper  # noqa: F401 - import is part of the native-stack probe
    import numpy  # noqa: F401 - import is part of the native-stack probe
    import onnxruntime  # noqa: F401 - import is part of the native-stack probe
    import tokenizers  # noqa: F401 - import is part of the native-stack probe
    from faster_whisper.audio import decode_audio

    with av.open(str(video.resolve())) as container:
        frames = list(container.decode(video=0))
    if not frames:
        raise ValueError("PyAV decoded no video frames")
    waveform = decode_audio(str(audio.resolve()), sampling_rate=16000)
    if len(waveform) == 0 or not bool((waveform != 0).any()):
        raise ValueError("faster-whisper decoded no non-silent audio")

    result = {
        "python": sys.version.split()[0],
        "packages": {
            name: metadata.version(name)
            for name in ("av", "ctranslate2", "faster-whisper", "numpy", "onnxruntime", "tokenizers")
        },
        "cpu_compute_types": sorted(ctranslate2.get_supported_compute_types("cpu")),
        "decoded_video_frames": len(frames),
        "decoded_audio_samples": len(waveform),
        "bundled_cudnn_absent": not bool(list(site_packages.rglob("cudnn*.dll"))),
    }
    if model is not None:
        if not (model / "model.bin").is_file():
            raise ValueError("Cached model directory is incomplete")
        from faster_whisper import WhisperModel

        started = time.monotonic()
        whisper = WhisperModel(
            str(model.resolve()),
            device="cpu",
            compute_type="int8",
            cpu_threads=4,
            local_files_only=True,
        )
        segments, info = whisper.transcribe(
            str(audio.resolve()),
            language="en",
            beam_size=1,
            vad_filter=False,
            condition_on_previous_text=False,
        )
        result["model_probe"] = {
            "decoded_duration_seconds": info.duration,
            "segments": sum(1 for _ in segments),
            "elapsed_seconds": round(time.monotonic() - started, 1),
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-packages", type=Path, required=True)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--require-no-cudnn", action="store_true")
    args = parser.parse_args()
    print(json.dumps(probe(args.site_packages, args.video, args.audio, args.model, args.require_no_cudnn), indent=2))


if __name__ == "__main__":
    main()
