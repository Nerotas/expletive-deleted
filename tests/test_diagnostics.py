import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.runtime import DependencyInventory, DependencyStatus
from backend.settings import AppSettings, SettingsStore, ensure_directories
from scripts.diagnostics import DiagnosticResult, collect_diagnostics, main


class DiagnosticsTests(unittest.TestCase):
    def test_collect_diagnostics_reports_each_configured_directory(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            settings = AppSettings.defaults(root)
            ensure_directories(settings.directories)
            store = SettingsStore(root / "settings.ini", settings)
            ready = DependencyStatus(
                id="ready",
                name="ready",
                state="ready",
                required_version=None,
                installed_version="1",
                path=root / "tool.exe",
                detail="ready",
                install_supported=True,
            )
            inventory = DependencyInventory(
                ffmpeg=DependencyStatus(**{**ready.__dict__, "id": "ffmpeg"}),
                ffprobe=DependencyStatus(**{**ready.__dict__, "id": "ffprobe"}),
                python=(DependencyStatus(**{**ready.__dict__, "id": "python:faster-whisper"}),),
                whisper_model=DependencyStatus(
                    **{**ready.__dict__, "id": "whisper:large-v3", "path": root / "model"}
                ),
            )

            with (
                patch("scripts.diagnostics.inspect_dependencies", return_value=inventory),
                patch("scripts.diagnostics.get_whisper_device_status", return_value=MagicMock(selected="cpu", compute_type="int8", detail="ready")),
            ):
                results = collect_diagnostics(store)

        names = {result.name for result in results}
        self.assertIn("directories.input", names)
        self.assertIn("directories.output", names)
        self.assertIn("directories.archive", names)
        self.assertIn("directories.transcripts", names)

    def test_warnings_do_not_fail_readiness(self):
        results = [
            DiagnosticResult("Required", True, "available"),
            DiagnosticResult("Optional", False, "missing", required=False),
        ]
        output = io.StringIO()

        with (
            patch("scripts.diagnostics.collect_diagnostics", return_value=results),
            patch("sys.stdout", output),
        ):
            exit_code = main()

        self.assertEqual(exit_code, 0)
        self.assertIn("[WARN] Optional: missing", output.getvalue())
        self.assertIn("Ready.", output.getvalue())

    def test_required_failure_returns_nonzero(self):
        results = [DiagnosticResult("FFmpeg", False, "not found")]
        output = io.StringIO()

        with (
            patch("scripts.diagnostics.collect_diagnostics", return_value=results),
            patch("sys.stdout", output),
        ):
            exit_code = main()

        self.assertEqual(exit_code, 1)
        self.assertIn("[FAIL] FFmpeg: not found", output.getvalue())
        self.assertIn("Not ready", output.getvalue())


if __name__ == "__main__":
    unittest.main()
