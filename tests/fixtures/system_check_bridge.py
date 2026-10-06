"""Offline system-check fixture using production dispatch and settings ownership."""

import os
import sys
import time
from dataclasses import replace
from pathlib import Path
from threading import Lock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.desktop.bridge import DesktopBridge
from backend.desktop.protocol import serve
from backend.service import BackendService
from backend.settings import AppSettings, SettingsStore

root = Path(os.environ["CENSOR_APP_DATA_DIR"]).parent
defaults = AppSettings.defaults(root / "media")
defaults = replace(defaults, onboarding=replace(defaults.onboarding, completed=True, last_step="finish"))
service = BackendService(SettingsStore(defaults=defaults))
guard = Lock()
checks = 0


def capabilities(settings, progress, cancellation):
    global checks
    with guard:
        checks += 1
        current = checks
        (root / "check-count.txt").write_text(str(checks))
    if current == 1:
        started = time.monotonic()
        progress("python_packages", "started", 0)
        deadline = time.monotonic() + 100
        while not (root / "release-first-check").exists():
            if cancellation.is_set():
                raise InterruptedError("Verification cancelled")
            if time.monotonic() >= deadline:
                raise RuntimeError("Smoke did not release the first check")
            time.sleep(0.02)
        (root / "first-check-finished").write_text("late response")
        progress("python_packages", "completed", (time.monotonic() - started) * 1000)
    return {
        "ready": True, "processing_ready": True, "app_runtime": "ready",
        "ffmpeg": True, "ffprobe": True, "whisper": True, "whisper_library": "faster-whisper",
        "whisper_model": "large-v3", "whisper_model_ready": True,
        "speech_model": "ready", "whisper_device": "cpu",
        "video_encoders": [], "ytdlp": True, "js_runtime": True,
    }


sys.stdin.reconfigure(encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
output = sys.stdout
sys.stdout = sys.stderr
bridge = DesktopBridge(service)
bridge.system_check.probe = capabilities
raise SystemExit(serve(bridge, output_stream=output))
