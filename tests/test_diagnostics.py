import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.settings import AppSettings, SettingsStore, ensure_directories
from scripts.diagnostics import DiagnosticResult, collect_diagnostics, main


class DiagnosticsTests(unittest.TestCase):
    def test_collect_diagnostics_reports_each_configured_directory(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            settings = AppSettings.defaults(root)
            ensure_directories(settings.directories)
            store = SettingsStore(root / "settings.json", settings)

            with (
                patch("scripts.diagnostics.find_ffmpeg", return_value=None),
                patch("scripts.diagnostics.find_ffprobe", return_value=None),
                patch("scripts.diagnostics.get_whisper_device_status"),
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