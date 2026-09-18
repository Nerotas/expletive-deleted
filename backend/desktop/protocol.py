"""Concurrent JSON-lines transport and Windows bridge startup."""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import TextIO
from backend.process_lifetime import contain_process_tree
from .bridge import DesktopBridge


def serve(
    bridge: DesktopBridge | None = None,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> int:
    bridge = bridge or DesktopBridge()
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    output_lock = Lock()

    def dispatch(line: str) -> None:
        request_id: object = None
        try:
            request = json.loads(line)
            request_id = request.get("id")
            result = bridge.handle(request["method"], request.get("params"))
            response = {"id": request_id, "ok": True, "result": result}
        except Exception as exc:
            response = {
                "id": request_id,
                "ok": False,
                "error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "code": getattr(exc, "code", None),
                    "diagnostic": getattr(exc, "diagnostic", None),
                },
            }
        with output_lock:
            output_stream.write(json.dumps(response, separators=(",", ":")) + "\n")
            output_stream.flush()

    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="desktop-bridge") as executor:
        try:
            for line in input_stream:
                if line.strip():
                    executor.submit(dispatch, line)
        finally:
            # Cancel active work before waiting for outstanding IPC requests.
            bridge.close()
    return 0


def main() -> int:
    contain_process_tree()
    # Electron sends UTF-8 JSON even when Windows uses a legacy pipe code page.
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    protocol_output = sys.stdout
    sys.stdout = sys.stderr
    return serve(output_stream=protocol_output)
