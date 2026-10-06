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


def capabilities():
    global checks
    with guard:
        checks += 1
        current = checks
        (root / "check-count.txt").write_text(str(checks))
    if current == 1:
        deadline = time.monotonic() + 100
        while not (root / "release-first-check").exists():
            if time.monotonic() >= deadline:
                raise RuntimeError("Smoke did not release the first check")
            time.sleep(0.02)
        (root / "first-check-finished").write_text("late response")
    return {
        "ready": current != 1, "processing_ready": current != 1, "app_runtime": "ready",
        "ffmpeg": True, "ffprobe": True, "whisper": True, "whisper_library": "faster-whisper",
        "whisper_model": "large-v3", "whisper_model_ready": current != 1,
        "speech_model": "ready" if current != 1 else "missing", "whisper_device": "cpu",
        "video_encoders": [], "ytdlp": True, "js_runtime": True,
    }


service.get_capabilities = capabilities
sys.stdin.reconfigure(encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
output = sys.stdout
sys.stdout = sys.stderr
raise SystemExit(serve(DesktopBridge(service), output_stream=output))
