import io
import json
import unittest
from unittest.mock import patch

from backend.runtime import DependencyInventory, DependencyStatus
from scripts.manage_dependencies import main


def status(dependency_id: str, state: str = "ready") -> DependencyStatus:
    return DependencyStatus(
        id=dependency_id,
        name=dependency_id,
        state=state,
        required_version=None,
        installed_version="1" if state == "ready" else None,
        path=None,
        detail=state,
        install_supported=True,
    )


class ManageDependenciesTests(unittest.TestCase):
    def test_status_json_does_not_build_or_execute_a_plan(self):
        inventory = DependencyInventory(
            ffmpeg=status("ffmpeg"),
            ffprobe=status("ffprobe"),
            python=(status("python:faster-whisper"),),
            whisper_model=status("whisper:large-v3"),
        )
        output = io.StringIO()

        with (
            patch("scripts.manage_dependencies.inspect_dependencies", return_value=inventory),
            patch("scripts.manage_dependencies.build_install_plan") as build,
            patch("scripts.manage_dependencies.execute_install_plan") as execute,
            patch("sys.stdout", output),
        ):
            exit_code = main(["status", "--json"])

        self.assertEqual(exit_code, 0)
        self.assertTrue(json.loads(output.getvalue())["ready"])
        build.assert_not_called()
        execute.assert_not_called()

    def test_plan_displays_source_and_approval_without_execution(self):
        output = io.StringIO()

        with (
            patch("scripts.manage_dependencies.execute_install_plan") as execute,
            patch("sys.stdout", output),
        ):
            exit_code = main(["plan", "--component", "whisper_model"])

        payload = output.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("Hugging Face / Systran", payload)
        self.assertIn("Approve this exact plan", payload)
        execute.assert_not_called()

    def test_install_rejects_unapproved_plan_before_execution(self):
        output = io.StringIO()

        with patch("sys.stdout", output):
            exit_code = main(
                [
                    "install",
                    "--component",
                    "whisper_model",
                    "--approve",
                    "wrong-plan",
                ]
            )

        self.assertEqual(exit_code, 1)
        self.assertIn("exact dependency install plan was not approved", output.getvalue())


if __name__ == "__main__":
    unittest.main()