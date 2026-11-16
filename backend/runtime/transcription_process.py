"""Cancellable private process for desktop Whisper inference."""

from __future__ import annotations

import json
import math
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Event, Thread
from typing import Any


_BOOTSTRAP = (
    "import json,sys; request=json.load(sys.stdin); "
    "sys.path[:]=request.pop('sys_path'); "
    "sys.prefix=request.pop('sys_prefix'); sys.exec_prefix=request.pop('sys_exec_prefix'); "
    "from backend.runtime.transcription_worker import run; run(request)"
)
_MAX_LINE = 1024 * 1024


def _validate_segment(segment: object) -> dict[str, Any]:
    if not isinstance(segment, dict) or not isinstance(segment.get("text"), str):
        raise RuntimeError("The transcription worker sent an invalid segment.")

    def times(value: dict) -> bool:
        start, end = value.get("start"), value.get("end")
        return (
            type(start) in (int, float) and type(end) in (int, float)
            and math.isfinite(start) and math.isfinite(end) and 0 <= start <= end
        )

    words = segment.get("words")
    if not times(segment) or not isinstance(words, list):
        raise RuntimeError("The transcription worker sent invalid timestamps.")
    if any(not isinstance(word, dict) or not isinstance(word.get("word"), str) or not times(word)
           for word in words):
        raise RuntimeError("The transcription worker sent an invalid word or timestamp.")
    return segment


def transcribe_in_process(
    library: str,
    model_name: str,
    requested_device: str,
    cache_dir: Path,
    media_path: str,
    batch_size: int,
    cancellation: Event,
    check_cancelled: Callable[[], None],
    on_ready: Callable[[], None] | None = None,
) -> Iterator[dict[str, Any]]:
    """Terminate the child when cancelled, even inside model loading or native inference."""
    check_cancelled()
    request = {
        "sys_path": sys.path, "library": library, "model": model_name,
        "sys_prefix": sys.prefix, "sys_exec_prefix": sys.exec_prefix,
        "device": requested_device, "cache_dir": str(cache_dir),
        "media_path": media_path, "batch_size": batch_size,
    }
    # A Windows venv executable is a launcher that spawns the actual interpreter.
    # Start that interpreter directly so terminating the child stops inference.
    executable = sys._base_executable if sys.platform == "win32" and sys.prefix != sys.base_prefix else sys.executable
    process = subprocess.Popen(
        [executable, "-B", "-c", _BOOTSTRAP],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, encoding="utf-8", errors="strict",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    messages: Queue[tuple[str, object]] = Queue(maxsize=2)
    stopped = Event()

    def enqueue(kind: str, value: object) -> None:
        while not stopped.is_set():
            try:
                messages.put((kind, value), timeout=0.1)
                return
            except Full:
                continue

    def read_output() -> None:
        try:
            while not stopped.is_set():
                line = process.stdout.readline(_MAX_LINE + 1)
                if not line:
                    enqueue("eof", None)
                    return
                if len(line) > _MAX_LINE or not line.endswith("\n"):
                    enqueue("invalid", "The transcription worker response exceeded its limit.")
                    return
                enqueue("line", line)
        except (OSError, UnicodeError, ValueError) as exc:
            enqueue("invalid", f"The transcription worker response could not be read: {exc}")

    reader = Thread(target=read_output, name="transcription-worker-output", daemon=True)
    completed = False
    ready = False
    try:
        process.stdin.write(json.dumps(request, ensure_ascii=True))
        process.stdin.close()
        reader.start()
        while True:
            check_cancelled()
            try:
                kind, value = messages.get(timeout=0.1)
            except Empty:
                continue
            check_cancelled()
            if kind == "eof":
                raise RuntimeError(f"Transcription worker stopped unexpectedly (exit code {process.poll()}). Retry the job.")
            if kind == "invalid":
                raise RuntimeError(str(value))
            try:
                message = json.loads(value)
            except (TypeError, ValueError) as exc:
                raise RuntimeError("The transcription worker sent an invalid response.") from exc
            if not isinstance(message, dict):
                raise RuntimeError("The transcription worker sent an invalid response.")
            event = message.get("type")
            if event == "ready" and not ready:
                ready = True
                if on_ready:
                    on_ready()
            elif event == "segment" and ready:
                yield _validate_segment(message.get("segment"))
            elif event == "completed" and ready:
                completed = True
                break
            elif event == "error" and isinstance(message.get("detail"), str):
                raise RuntimeError(
                    "Transcription failed. If memory is limited, close other apps and retry. "
                    f"No automatic mode change was attempted. Details: {message['detail']}"
                )
            else:
                raise RuntimeError("The transcription worker sent an unexpected response.")
    finally:
        stopped.set()
        if process.poll() is None and (not completed or cancellation.is_set()):
            process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
        if not process.stdin.closed:
            process.stdin.close()
        if reader.ident is not None:
            reader.join(timeout=2)
        process.stdout.close()
    if process.returncode != 0:
        raise RuntimeError(f"Transcription worker exited with code {process.returncode}. Retry the job.")
    check_cancelled()
