"""Private, read-only verifier; native imports cannot block the desktop bridge."""

import json
import sys

from backend.service.capabilities import get_capabilities
from backend.settings.serialization import settings_from_dict


def run(settings: dict) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    output = sys.stdout
    # Optional packages may print. Only our narrow JSON protocol reaches the parent.
    sys.stdout = sys.stderr

    def send(value):
        output.write(json.dumps(value, allow_nan=False) + "\n")
        output.flush()

    def progress(stage, state, duration_ms):
        send({"type": "progress", "stage": stage, "state": state, "duration_ms": duration_ms})

    try:
        capabilities = get_capabilities(settings_from_dict(settings), progress=progress)
        send({"type": "result", "capabilities": capabilities})
    except Exception:
        # Do not retain exception text containing machine paths or user settings.
        send({"type": "error"})
