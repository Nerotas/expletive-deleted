import json
import tempfile
import time
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import MagicMock, patch

from backend.runtime.dependencies import (
    DependencyConsentError,
    DependencyInstallError,
    DependencyNotReadyError,
    DependencyInventory,
    DependencyStatus,
    PYTHON_DEPENDENCIES,
    PYTHON_REQUIREMENTS,
    WHISPER_MODEL_FILES,
    WHISPER_MODEL_REVISION,
    _run_action,
    build_install_plan,
    execute_install_plan,
    inspect_executable,
    inspect_python_dependencies,
    inspect_whisper_model,
    require_whisper_model_path,
)
from scripts.desktop_bridge import DesktopBridge
from backend.runtime.environment import get_managed_ffmpeg_manifest_path, get_managed_ffmpeg_paths


class DependencyInventoryTests(unittest.TestCase):
    def test_managed_ffmpeg_manifest_paths_are_canonicalized(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            binaries = root / "binaries"
            binaries.mkdir()
            ffmpeg = binaries / "ffmpeg.exe"
            ffprobe = binaries / "ffprobe.exe"
            ffmpeg.write_text("")
            ffprobe.write_text("")
            manifest = get_managed_ffmpeg_manifest_path(root)
            manifest.write_text(
                json.dumps({"ffmpeg": str(ffmpeg), "ffprobe": str(ffprobe)}),
                encoding="utf-8",
            )

            discovered_ffmpeg, discovered_ffprobe = get_managed_ffmpeg_paths(root)
            self.assertEqual(Path(discovered_ffmpeg), ffmpeg.resolve())
            self.assertEqual(Path(discovered_ffprobe), ffprobe.resolve())

    def test_missing_executable_is_reported_without_running_a_command(self):
        with patch("backend.runtime.dependencies.subprocess.run") as run:
            status = inspect_executable("ffmpeg", "FFmpeg", None)

        self.assertEqual(status.state, "missing")
        self.assertTrue(status.install_supported)
        run.assert_not_called()

    def test_executable_version_is_reported(self):
        completed = unittest.mock.MagicMock(
            returncode=0,
            stdout="ffmpeg version 8.0-full_build Copyright\n",
            stderr="",
        )
        with patch("backend.runtime.dependencies.subprocess.run", return_value=completed):
            status = inspect_executable("ffmpeg", "FFmpeg", "C:\\ffmpeg.exe")

        self.assertEqual(status.state, "ready")
        self.assertEqual(status.installed_version, "8.0-full_build")

    def test_unsupported_executable_version_is_invalid(self):
        completed = MagicMock(
            returncode=0,
            stdout="ffmpeg version 7.1 Copyright\n",
            stderr="",
        )
        with patch("backend.runtime.dependencies.subprocess.run", return_value=completed):
            status = inspect_executable("ffmpeg", "FFmpeg", "C:\\ffmpeg.exe", "8.0")

        self.assertEqual(status.state, "invalid")
        self.assertIn("requires 8.0", status.detail)

    def test_newer_ffmpeg_release_is_supported(self):
        completed = MagicMock(
            returncode=0,
            stdout="ffmpeg version 9.0.1-full_build Copyright\n",
            stderr="",
        )
        with patch("backend.runtime.dependencies.subprocess.run", return_value=completed):
            status = inspect_executable(
                "ffmpeg", "FFmpeg", "C:\\ffmpeg.exe", "8.0 or later"
            )

        self.assertTrue(status.ready)
        self.assertEqual(status.installed_version, "9.0.1-full_build")

    def test_python_dependency_version_mismatch_is_invalid(self):
        required = dict(PYTHON_DEPENDENCIES)

        with patch(
            "backend.runtime.dependencies.importlib.metadata.version",
            side_effect=lambda name: "0.0.0" if name == "faster-whisper" else required[name],
        ):
            statuses = inspect_python_dependencies()

        faster_whisper = next(status for status in statuses if status.id == "python:faster-whisper")
        self.assertEqual(faster_whisper.state, "invalid")
        self.assertEqual(faster_whisper.required_version, required["faster-whisper"])

    def test_model_verification_is_local_only_and_revision_pinned(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            model_path = Path(temporary_directory) / "model"
            model_path.mkdir()
            for name in WHISPER_MODEL_FILES:
                (model_path / name).write_text("test")

            with patch(
                "faster_whisper.utils.download_model",
                return_value=str(model_path),
            ) as download:
                status = inspect_whisper_model(Path(temporary_directory) / "cache")

        self.assertEqual(status.state, "ready")
        self.assertEqual(status.installed_version, WHISPER_MODEL_REVISION)
        self.assertTrue(download.call_args.kwargs["local_files_only"])
        self.assertEqual(download.call_args.kwargs["revision"], WHISPER_MODEL_REVISION)

    def test_incomplete_model_cache_is_invalid(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            model_path = Path(temporary_directory) / "model"
            model_path.mkdir()
            (model_path / "config.json").write_text("{}")
            with patch("faster_whisper.utils.download_model", return_value=str(model_path)):
                status = inspect_whisper_model(Path(temporary_directory) / "cache")

        self.assertEqual(status.state, "invalid")
        self.assertIn("model.bin", status.detail)

    def test_processing_requires_verified_model_without_downloading(self):
        missing = DependencyStatus(
            id="whisper:large-v3",
            name="Whisper large-v3 model",
            state="missing",
            required_version=WHISPER_MODEL_REVISION,
            installed_version=None,
            path=None,
            detail="not cached",
            install_supported=True,
        )
        with (
            patch("backend.runtime.dependencies.inspect_whisper_model", return_value=missing),
            self.assertRaisesRegex(DependencyNotReadyError, "Install it from the app setup"),
        ):
            require_whisper_model_path()


class DependencyPlanTests(unittest.TestCase):
    def test_plan_is_stable_inspectable_and_version_pinned(self):
        kwargs = {
            "python_executable": Path("C:\\Python\\python.exe"),
            "cache_dir": Path("C:\\models"),
            "platform_name": "Windows",
        }

        first = build_install_plan(["ffmpeg", "python", "whisper_model"], **kwargs)
        second = build_install_plan(["ffmpeg", "python", "whisper_model"], **kwargs)

        self.assertEqual(first.id, second.id)
        self.assertEqual(len(first.actions), 4)
        self.assertIn("static-ffmpeg", first.actions[0].source_url)
        self.assertIn("static-ffmpeg==3.0", first.actions[0].command)
        self.assertIn("scripts.download_ffmpeg_runtime", first.actions[1].command)
        self.assertTrue(all(requirement in first.actions[2].command for requirement in PYTHON_REQUIREMENTS))
        self.assertIn(WHISPER_MODEL_REVISION, first.actions[3].source_url)

    def test_non_windows_ffmpeg_plan_is_supported(self):
        plan = build_install_plan(["ffmpeg"], platform_name="Linux")
        self.assertEqual(len(plan.actions), 2)

    def test_exact_plan_approval_is_required_before_execution(self):
        plan = build_install_plan(["python"], python_executable=Path("C:\\python.exe"))

        with (
            patch("backend.runtime.dependencies._run_action") as run,
            self.assertRaises(DependencyConsentError),
        ):
            execute_install_plan(plan, approved_plan_id="different-plan")

        run.assert_not_called()

    def test_success_emits_stages_and_verifies_dependencies(self):
        plan = build_install_plan(["python"], python_executable=Path("C:\\python.exe"))
        ready_python = tuple(
            DependencyStatus(
                id=f"python:{name}",
                name=name,
                state="ready",
                required_version=version,
                installed_version=version,
                path=None,
                detail="ready",
                install_supported=True,
            )
            for name, version in PYTHON_DEPENDENCIES
        )
        placeholder = DependencyStatus(
            id="placeholder",
            name="placeholder",
            state="missing",
            required_version=None,
            installed_version=None,
            path=None,
            detail="unused",
            install_supported=True,
        )
        inventory = DependencyInventory(
            ffmpeg=DependencyStatus(**{**placeholder.__dict__, "id": "ffmpeg"}),
            ffprobe=DependencyStatus(**{**placeholder.__dict__, "id": "ffprobe"}),
            python=ready_python,
            whisper_model=DependencyStatus(**{**placeholder.__dict__, "id": "whisper:large-v3"}),
        )
        events = []

        with (
            patch("backend.runtime.dependencies._run_action", return_value="installed"),
            patch("backend.runtime.dependencies.inspect_dependencies", return_value=inventory),
        ):
            results = execute_install_plan(
                plan,
                approved_plan_id=plan.id,
                progress_callback=events.append,
            )

        self.assertEqual(results[0].detail, "installed")
        self.assertEqual([event.phase for event in events], ["starting", "verifying", "completed"])

    def test_failed_post_install_verification_is_reported(self):
        plan = build_install_plan(["python"], python_executable=Path("C:\\python.exe"))
        missing = DependencyStatus(
            id="python:faster-whisper",
            name="faster-whisper",
            state="missing",
            required_version="1.2.1",
            installed_version=None,
            path=None,
            detail="not installed",
            install_supported=True,
        )
        other_python = tuple(
            DependencyStatus(
                id=f"python:{name}",
                name=name,
                state="ready",
                required_version=version,
                installed_version=version,
                path=None,
                detail="ready",
                install_supported=True,
            )
            for name, version in PYTHON_DEPENDENCIES
            if name != "faster-whisper"
        )
        placeholder = DependencyStatus(
            id="ffmpeg",
            name="unused",
            state="missing",
            required_version=None,
            installed_version=None,
            path=None,
            detail="unused",
            install_supported=True,
        )
        inventory = DependencyInventory(
            ffmpeg=placeholder,
            ffprobe=DependencyStatus(**{**placeholder.__dict__, "id": "ffprobe"}),
            python=(missing, *other_python),
            whisper_model=DependencyStatus(**{**placeholder.__dict__, "id": "whisper:large-v3"}),
        )

        with (
            patch("backend.runtime.dependencies._run_action", return_value="installed"),
            patch("backend.runtime.dependencies.inspect_dependencies", return_value=inventory),
            self.assertRaisesRegex(DependencyInstallError, "did not verify"),
        ):
            execute_install_plan(plan, approved_plan_id=plan.id)

    def test_running_child_process_can_be_cancelled(self):
        plan = build_install_plan(["whisper_model"], cache_dir=Path("C:\\models"))
        process = MagicMock()
        process.wait.return_value = 0
        cancellation = Event()
        cancellation.set()
        events = []

        with (
            patch("backend.runtime.dependencies.subprocess.Popen", return_value=process),
            self.assertRaisesRegex(DependencyInstallError, "cancelled"),
        ):
            _run_action(plan.actions[0], cancellation, events.append)

        process.terminate.assert_called_once()
        self.assertEqual(events[-1].phase, "cancelled")

    def test_requirements_file_matches_dependency_descriptors(self):
        requirements_path = Path(__file__).resolve().parents[1] / "requirements.txt"
        requirements = tuple(
            line.strip()
            for line in requirements_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        )
        self.assertEqual(requirements, PYTHON_REQUIREMENTS)

    def test_install_tracking_starts_and_reports_background_state(self):
        bridge = DesktopBridge()
        plan = build_install_plan(["python"], python_executable=Path("C:\\python.exe"))
        bridge._install_plans[plan.id] = plan

        running = Event()
        finish = Event()

        def fake_run(plan_arg, **kwargs):
            progress_callback = kwargs["progress_callback"]
            progress_callback(type("Event", (), {"action_id": plan_arg.actions[0].id, "phase": "starting", "message": "Installing Python dependencies", "completed_bytes": None, "total_bytes": None})())
            progress_callback(type("Event", (), {"action_id": plan_arg.actions[0].id, "phase": "running", "message": "Installing Python dependencies", "completed_bytes": 1024, "total_bytes": 4096})())
            running.set()
            finish.wait(1)
            progress_callback(type("Event", (), {"action_id": plan_arg.actions[0].id, "phase": "completed", "message": "Installation verified", "completed_bytes": 4096, "total_bytes": 4096})())
            return (type("Result", (), {"action_id": plan_arg.actions[0].id, "dependency_ids": plan_arg.actions[0].dependency_ids, "detail": "installed"})(),)

        with patch("scripts.desktop_bridge.execute_install_plan", side_effect=fake_run):
            started = bridge.handle("dependencies.install", {"plan_id": plan.id})
            self.assertIn("install_id", started)
            self.assertEqual(started["status"], "running")

            self.assertTrue(running.wait(1))
            status = bridge.handle("dependencies.status", {"install_id": started["install_id"]})
            self.assertEqual(status["phase"], "running")
            self.assertEqual(status["message"], "Installing Python dependencies")
            self.assertEqual(status["completed_bytes"], 1024)
            self.assertEqual(status["total_bytes"], 4096)

            finish.set()

            deadline = time.monotonic() + 2
            status = bridge.handle("dependencies.status", {"install_id": started["install_id"]})
            while status["status"] not in ("completed", "failed") and time.monotonic() < deadline:
                status = bridge.handle("dependencies.status", {"install_id": started["install_id"]})
            self.assertEqual(status["status"], "completed")

        bridge._install_executor.shutdown(wait=True)
        bridge.close()


if __name__ == "__main__":
    unittest.main()
