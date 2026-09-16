"""Offline native-smoke backend: real job lifecycle with a controllable encoder."""

import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path


repository = Path(os.environ["SHUTDOWN_TEST_REPO"])
test_root = Path(os.environ["SHUTDOWN_TEST_ROOT"])
sys.path.insert(0, str(repository))
from backend.jobs import JobManager
from backend.service import BackendService
from backend.settings import AppSettings, DirectorySettings, SettingsStore

spec = importlib.util.spec_from_file_location("actual_desktop_bridge", repository / "scripts" / "desktop_bridge.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ControlledEncoder:
    def __init__(self, source, output, *args, **kwargs):
        self.output = Path(output)
        self.cancellation = kwargs["cancellation"]

    def process_verified_transcript(self):
        self.output.write_bytes(b"incomplete synthetic media")
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"],
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        (test_root / "child.pid").write_text(str(child.pid))
        (test_root / "started").touch()
        if os.environ.get("SHUTDOWN_TEST_HANG") == "1":
            time.sleep(120)  # Exercise Electron's bounded fallback and the Windows Job Object.
        self.cancellation.wait(30)
        child.terminate()
        child.wait(timeout=5)
        (test_root / "cancelled").touch()
        return False


def make_bridge():
    settings = AppSettings(directories=DirectorySettings(
        input=test_root / "Ready", output=test_root / "Finished",
        archive=test_root / "Processed", transcripts=test_root / "Transcripts",
    ))
    service = BackendService(SettingsStore(test_root / "settings.ini", settings),
                             manager_factory=lambda config: JobManager(config, censor_factory=ControlledEncoder))
    return module.DesktopBridge(service)


if __name__ == "__main__":
    module.contain_process_tree()
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    protocol_output = sys.stdout
    sys.stdout = sys.stderr
    module.serve(make_bridge(), output_stream=protocol_output)
