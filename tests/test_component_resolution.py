"""Regression checks for the paths inspected, installed, and used by jobs."""

import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.censor.engine import ProfanityCensor
from backend.jobs.downloads import DownloadManager, DownloadRecord, _javascript_runtime_arguments
from backend.runtime.dependencies import (
    DependencyInventory, DependencyStatus, PYTHON_DEPENDENCIES,
    build_install_plan, execute_install_plan, inspect_dependencies,
    inspect_python_dependencies, _default_js_runtime_executable,
)
from backend.runtime.environment import (
    get_managed_deno_path, get_managed_ytdlp_path,
    resolve_deno_path, resolve_ytdlp_path,
)
from backend.runtime.python_imports import inspect_python_imports
from backend.settings import AppSettings


class ComponentResolutionTests(unittest.TestCase):
    def test_download_rejects_split_media_tool_folders_before_starting_ytdlp(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ytdlp = root / "yt-dlp.exe"
            ytdlp.touch()
            settings = AppSettings.defaults(root / "media")
            settings = replace(settings, runtime=replace(settings.runtime,
                ytdlp_path=ytdlp, ffmpeg_path=root / "one/ffmpeg.exe", ffprobe_path=root / "two/ffprobe.exe",
            ))
            manager = DownloadManager(settings)
            manager._records["job"] = DownloadRecord("job", "https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ")
            manager._events["job"] = []
            try:
                with patch("backend.jobs.downloads.subprocess.Popen") as run:
                    manager._run("job")
                failed = manager.list()[0]
                self.assertEqual(failed.status, "failed")
                self.assertIn("same folder", failed.error.detail)
                run.assert_not_called()
            finally:
                manager.close()

    def test_successful_import_probe_ignores_package_console_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "better_profanity.py").write_text("print('package output')\n")
            with patch.object(sys, "path", [str(root), *sys.path]):
                self.assertEqual(inspect_python_imports(["better-profanity"]), {"better-profanity": None})

    def test_media_checks_engine_and_downloader_preserve_individual_overrides(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            defaults = (str(root / "managed/ffmpeg.exe"), str(root / "managed/ffprobe.exe"))
            custom = (root / "custom/ffmpeg.exe", root / "custom/ffprobe.exe")
            policy = MagicMock()
            policy.load.return_value.censor_words = set()
            policy.load.return_value.exclusions = set()
            for ffmpeg, ffprobe in ((None, None), (custom[0], None), (None, custom[1]), custom):
                with (
                    self.subTest(ffmpeg=ffmpeg, ffprobe=ffprobe),
                    patch("backend.runtime.environment.find_ffmpeg", return_value=defaults[0]),
                    patch("backend.runtime.environment.find_ffprobe", return_value=defaults[1]),
                    patch("backend.runtime.dependencies.inspect_executable") as inspect,
                    patch("backend.runtime.dependencies.inspect_python_dependencies", return_value=()),
                    patch("backend.runtime.dependencies.inspect_whisper_model"),
                    patch("backend.runtime.dependencies.inspect_ytdlp"),
                    patch("backend.runtime.dependencies.inspect_js_runtime"),
                ):
                    inspect_dependencies(ffmpeg_bin=ffmpeg, ffprobe_bin=ffprobe)
                    checked = tuple(call.args[2] for call in inspect.call_args_list)
                    settings = AppSettings.defaults(root / "media")
                    settings = replace(settings, runtime=replace(settings.runtime, ffmpeg_path=ffmpeg, ffprobe_path=ffprobe))
                    manager = DownloadManager(settings)
                    try:
                        used = tuple(str(path) for path in manager._runtime_media_tools())
                    finally:
                        manager.close()
                    engine = ProfanityCensor("input", "output", ffmpeg_bin=ffmpeg, ffprobe_bin=ffprobe, policy_store=policy)
                    self.assertEqual(checked, (str(ffmpeg or defaults[0]), str(ffprobe or defaults[1])))
                    self.assertEqual(used, checked)
                    self.assertEqual((engine.ffmpeg_bin, engine.ffprobe_bin), checked)

    def test_runtime_overrides_do_not_change_managed_install_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            external_ytdlp, external_deno = root / "external-ytdlp.exe", root / "external-deno.exe"
            external_deno.touch()
            with patch.dict("os.environ", {"CENSOR_YTDLP": str(external_ytdlp), "CENSOR_DENO": str(external_deno)}):
                self.assertEqual(get_managed_ytdlp_path(root), (root / "dependencies/yt-dlp/yt-dlp.exe").resolve())
                self.assertEqual(get_managed_deno_path(root), (root / "dependencies/deno/deno.exe").resolve())
                self.assertEqual(resolve_ytdlp_path(), external_ytdlp.resolve())
                self.assertEqual(resolve_ytdlp_path(root / "custom.exe"), (root / "custom.exe").resolve())
                self.assertEqual(resolve_deno_path(), external_deno.resolve())
                self.assertEqual(_default_js_runtime_executable(), str(external_deno.resolve()))
                self.assertEqual(_javascript_runtime_arguments(), ("--js-runtimes", f"deno:{external_deno.resolve()}"))

    def test_install_verifies_approved_destinations_despite_runtime_overrides(self):
        ready = lambda name: DependencyStatus(name, name, "ready", None, None, None, "fixture", False)
        inventory = DependencyInventory(ready("ffmpeg"), ready("ffprobe"), (), ready("whisper:large-v3"), ready("ytdlp"), ready("js_runtime"))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (
                patch.dict("os.environ", {"CENSOR_YTDLP": str(root / "external.exe"), "CENSOR_DENO": str(root / "external-deno.exe")}),
                patch("backend.runtime.dependencies.inspect_python_dependencies", return_value=()),
                patch("backend.runtime.dependencies._run_action"),
                patch("backend.runtime.dependencies.inspect_dependencies", return_value=inventory) as inspect,
            ):
                plan = build_install_plan(["ytdlp", "js_runtime"], runtime_root=root, platform_name="Windows")
                execute_install_plan(plan, approved_plan_id=plan.id)
                for action in plan.actions:
                    self.assertEqual(action.command[action.command.index("--root") + 1], str(root.resolve()))
                self.assertEqual(inspect.call_args_list[0].kwargs["ytdlp_bin"], plan.actions[0].destination / "yt-dlp.exe")
                self.assertEqual(inspect.call_args_list[1].kwargs["js_runtime_bin"], plan.actions[1].destination / "deno.exe")

    def test_matching_package_metadata_cannot_hide_an_import_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "better_profanity.py").write_text("raise ImportError('broken test package')\n")
            with (
                patch.object(sys, "path", [str(root), *sys.path]),
                patch("backend.runtime.dependencies.importlib.metadata.version", side_effect=lambda name: dict(PYTHON_DEPENDENCIES)[name] if name == "better-profanity" else "0"),
            ):
                statuses = inspect_python_dependencies()
            status = next(item for item in statuses if item.name == "better-profanity")
            self.assertEqual(status.state, "invalid")
            self.assertIn("broken test package", status.detail)

    def test_import_probe_uses_processing_interpreter_and_paths_and_has_a_timeout(self):
        with patch("backend.runtime.python_imports.subprocess.run", side_effect=subprocess.TimeoutExpired("python", 30)) as run:
            result = inspect_python_imports(["better-profanity"])
        self.assertIn("timed out", result["better-profanity"])
        self.assertEqual(run.call_args.args[0][0], sys.executable)
        self.assertEqual(json.loads(run.call_args.kwargs["input"])["sys_path"], sys.path)
        self.assertEqual(run.call_args.kwargs["timeout"], 30)

    def test_crashed_or_malformed_import_probe_never_reports_ready(self):
        for result in (
            MagicMock(returncode=1, stdout=""),
            MagicMock(returncode=0, stdout="{}"),
            MagicMock(returncode=0, stdout='{"better-profanity": true}'),
        ):
            with self.subTest(result=result), patch("backend.runtime.python_imports.subprocess.run", return_value=result):
                self.assertIsInstance(inspect_python_imports(["better-profanity"])["better-profanity"], str)
