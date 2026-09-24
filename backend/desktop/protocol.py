"""Concurrent JSON-lines transport and Windows bridge startup."""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import TextIO
from backend.process_lifetime import contain_process_tree
from .bridge import DesktopBridge

# These handlers only read state, set cancellation flags or schedule an approved
# worker. Dispatch inline: ordinary worker saturation cannot queue control reads.
CONTROL_METHODS = frozenset({"dependencies.status", "dependencies.active", "dependencies.cancel", "dependencies.install"})


def serve(
    bridge: DesktopBridge | None = None,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> int:
    bridge = bridge or DesktopBridge()
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    output_lock = Lock()

    def dispatch(request: object) -> None:
        request_id: object = None
        try:
            if not isinstance(request, dict):
                raise ValueError("Expected a protocol request object")
            candidate_id = request.get("id")
            if type(candidate_id) is not int or not 0 < candidate_id <= 2**53 - 1:
                raise ValueError("Expected a positive protocol request id")
            request_id = candidate_id
            if not isinstance(request.get("method"), str):
                raise ValueError("Expected a protocol method")
            result = bridge.handle(request["method"], request.get("params"))
            response = {"id": request_id, "ok": True, "result": result}
            try:
                encoded = json.dumps(response, separators=(",", ":"), allow_nan=False)
            except (TypeError, ValueError) as exc:
                error = ValueError("The local service could not encode its response")
                error.code = "protocol_error"
                raise error from exc
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
            try:
                encoded = json.dumps(response, separators=(",", ":"), allow_nan=False)
            except (TypeError, ValueError):
                encoded = json.dumps({"id": request_id, "ok": False, "error": {
                    "message": "The local service could not encode its response", "code": "protocol_error"}}, allow_nan=False)
        with output_lock:
            output_stream.write(encoded + "\n")
            output_stream.flush()

    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="desktop-bridge") as executor:
        try:
            for line in input_stream:
                if line.strip():
                    try:
                        request = json.loads(line)
                    except ValueError:
                        request = None
                    method = request.get("method") if isinstance(request, dict) else None
                    if isinstance(method, str) and method in CONTROL_METHODS:
                        dispatch(request)
                    else:
                        executor.submit(dispatch, request)
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
