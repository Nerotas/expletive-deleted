"""Private transcription worker; the parent owns media and transcript publication."""

import json
import sys
from pathlib import Path

from .transcription import load_transcription_model, transcribe_segments


def run(request: dict) -> None:
    output = sys.stdout
    sys.stdout = sys.stderr

    def send(value: dict) -> None:
        output.write(json.dumps(value, allow_nan=False, ensure_ascii=True) + "\n")
        output.flush()

    try:
        model, _ = load_transcription_model(
            request["library"], request["model"], request["device"], Path(request["cache_dir"]),
        )
        send({"type": "ready"})
        for segment in transcribe_segments(
            model, request["library"], request["media_path"],
            experimental_batch_size=request["batch_size"],
            on_prepared=lambda: send({"type": "transcribing"}),
        ):
            send({"type": "segment", "segment": segment})
        send({"type": "completed"})
    except Exception as exc:
        send({"type": "error", "detail": str(exc), "error_type": type(exc).__name__})
