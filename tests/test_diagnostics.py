import io
import unittest
from unittest.mock import patch

from scripts.diagnostics import DiagnosticResult, main


class DiagnosticsTests(unittest.TestCase):
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