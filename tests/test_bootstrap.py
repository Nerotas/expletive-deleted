import unittest
from unittest.mock import patch

from scripts import bootstrap


class BootstrapTests(unittest.TestCase):
    def test_install_approved_runtime_prompts_and_executes_the_current_plan(self):
        plan = bootstrap.build_install_plan(
            ["ffmpeg"],
            python_executable=bootstrap.VENV_PYTHON,
            runtime_root=bootstrap.get_application_runtime_root(),
        )
        with (
            patch.object(bootstrap, "initialize_application_settings", return_value=("settings.ini", ())),
            patch.object(bootstrap, "_development_runtime_components", return_value=["ffmpeg"]),
            patch.object(bootstrap, "get_whisper_cache_dir", return_value=bootstrap.PROJECT_ROOT / "whisper-cache"),
            patch.object(bootstrap, "get_external_whisper_cache_dir", return_value=bootstrap.PROJECT_ROOT / "missing-cache"),
            patch.object(bootstrap, "get_directory_size", return_value=0),
            patch.object(bootstrap, "get_application_runtime_root", return_value=bootstrap.PROJECT_ROOT / "runtime"),
            patch.object(bootstrap, "build_install_plan", return_value=plan),
            patch.object(bootstrap, "find_ffmpeg", return_value=None),
            patch.object(bootstrap, "find_ffprobe", return_value=None),
            patch.object(bootstrap, "run", return_value=0),
            patch.object(bootstrap, "VENV_PYTHON", bootstrap.PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"),
            patch.object(bootstrap, "execute_install_plan", return_value=()) as execute_install,
            patch("builtins.input", return_value="y"),
            patch("sys.argv", ["setup.py", "--install-approved-runtime"]),
        ):
            self.assertEqual(bootstrap.main(), 0)

        execute_install.assert_called_once()
        self.assertEqual(execute_install.call_args.kwargs["approved_plan_id"], plan.id)

    def test_install_approved_runtime_can_be_declined(self):
        with (
            patch.object(bootstrap, "initialize_application_settings", return_value=("settings.ini", ())),
            patch.object(bootstrap, "_development_runtime_components", return_value=["ffmpeg"]),
            patch.object(bootstrap, "get_whisper_cache_dir", return_value=bootstrap.PROJECT_ROOT / "whisper-cache"),
            patch.object(bootstrap, "get_external_whisper_cache_dir", return_value=bootstrap.PROJECT_ROOT / "missing-cache"),
            patch.object(bootstrap, "get_directory_size", return_value=0),
            patch.object(bootstrap, "get_application_runtime_root", return_value=bootstrap.PROJECT_ROOT / "runtime"),
            patch.object(bootstrap, "build_install_plan") as build_plan,
            patch.object(bootstrap, "execute_install_plan") as execute_install,
            patch.object(bootstrap, "find_ffmpeg", return_value=None),
            patch.object(bootstrap, "find_ffprobe", return_value=None),
            patch.object(bootstrap, "run", return_value=0),
            patch("builtins.input", return_value="n"),
            patch("sys.argv", ["setup.py", "--install-approved-runtime"]),
        ):
            self.assertEqual(bootstrap.main(), 0)

        build_plan.assert_called_once()
        execute_install.assert_not_called()


if __name__ == "__main__":
    unittest.main()