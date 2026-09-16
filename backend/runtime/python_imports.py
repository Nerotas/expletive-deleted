"""Bounded import checks using the processing interpreter and search path."""

from __future__ import annotations

import json
import subprocess
import sys


PYTHON_MODULES = {
    "faster-whisper": "faster_whisper",
    "better-profanity": "better_profanity",
    "numpy": "numpy",
    "ctranslate2": "ctranslate2",
    "av": "av",
    "huggingface-hub": "huggingface_hub",
}

# A fresh process detects broken files/native libraries even if the bridge has
# already imported an older copy. Redirect package output away from the protocol.
_IMPORT_PROBE = """
import contextlib, importlib, io, json, sys
request = json.load(sys.stdin)
sys.path[:] = request['sys_path']
results = {}
for distribution, module in request['modules'].items():
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            importlib.import_module(module)
        results[distribution] = None
    except BaseException as error:
        results[distribution] = type(error).__name__ + ': ' + str(error)[:400]
print(json.dumps(results))
"""


def inspect_python_imports(distributions: list[str]) -> dict[str, str | None]:
    """Return import errors without loading optional packages into the bridge."""
    if not distributions:
        return {}
    try:
        result = subprocess.run(
            [sys.executable, "-c", _IMPORT_PROBE],
            input=json.dumps({
                "sys_path": sys.path,
                "modules": {name: PYTHON_MODULES[name] for name in distributions},
            }),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            raise ValueError(f"Import check exited with code {result.returncode}")
        payload = json.loads(result.stdout)
        if not isinstance(payload, dict) or set(payload) != set(distributions):
            raise ValueError("Import check returned an incomplete result")
        if any(value is not None and not isinstance(value, str) for value in payload.values()):
            raise ValueError("Import check returned an invalid result")
        return payload
    except subprocess.TimeoutExpired:
        detail = "Python package import check timed out after 30 seconds"
    except (OSError, ValueError) as error:
        detail = f"Python package import check failed: {error}"
    return dict.fromkeys(distributions, detail)
