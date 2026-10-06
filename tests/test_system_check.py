"""Background checks retain eventual results without stale readiness or logs."""

import json
import subprocess
import sys
import tempfile
import time
import unittest
from dataclasses import replace
from io import StringIO
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.desktop.system_check import SystemCheckController, run_check
from backend.runtime.check_progress import STAGES, check_stage
from backend.settings import AppSettings


class SystemCheckTests(unittest.TestCase):
    def setup_check(self, probe):
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        service = SimpleNamespace(settings=AppSettings.defaults(Path(root.name)))
        controller = SystemCheckController(service, probe=probe)
        self.addCleanup(controller.close)
        return controller, service

    def wait_for(self, predicate):
        deadline = time.monotonic() + 3
        while not predicate():
            if time.monotonic() >= deadline:
                self.fail("Background verifier did not settle")
            time.sleep(0.005)

    def test_one_running_check_and_late_success_are_reused_on_reconnect(self):
        entered, release = Event(), Event()
        self.addCleanup(release.set)
        calls = []

        def probe(settings, progress, cancellation):
            calls.append(settings)
            progress("python_packages", "started", 0)
            entered.set()
            release.wait(3)
            progress("python_packages", "completed", 61000)
            return {"ready": True, "processing_ready": True}

        controller, _ = self.setup_check(probe)
        initial = controller.start()
        self.assertTrue(entered.wait(1))
        for _ in range(10):
            self.assertEqual(controller.start()["check_id"], initial["check_id"])
        self.assertIsNone(controller.status()["capabilities"])
        self.assertEqual(controller.status()["stage"], "python_packages")
        release.set()
        self.wait_for(lambda: controller.status()["status"] == "completed")
        self.assertTrue(controller.start()["capabilities"]["ready"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(controller.status()["timings"], {"python_packages": 61000})

    def test_settings_changes_queue_latest_snapshot_and_never_publish_old_results(self):
        entered, release = Event(), Event()
        self.addCleanup(release.set)
        calls = []

        def probe(settings, progress, cancellation):
            calls.append(settings.processing.device)
            if len(calls) == 1:
                entered.set()
                release.wait(3)
            return {"ready": settings.processing.device != "cpu", "processing_ready": settings.processing.device != "cpu"}

        controller, service = self.setup_check(probe)
        first = controller.start()
        self.assertTrue(entered.wait(1))
        service.settings = replace(service.settings, processing=replace(service.settings.processing, device="cpu"))
        queued = controller.start()
        self.assertNotEqual(first["check_id"], queued["check_id"])
        self.assertEqual(queued["stage"], "waiting_previous_check")
        for _ in range(5):
            self.assertEqual(controller.start(refresh=True)["check_id"], queued["check_id"])
        release.set()
        self.wait_for(lambda: controller.status()["status"] == "completed")
        self.assertEqual(calls, ["auto", "cpu"])
        self.assertFalse(controller.status()["capabilities"]["ready"])

    def test_change_after_completion_invalidates_cached_readiness(self):
        controller, service = self.setup_check(lambda settings, progress, cancellation: {"ready": settings.processing.device != "cpu"})
        original = controller.start()
        self.wait_for(lambda: controller.status()["status"] == "completed")
        service.settings = replace(service.settings, processing=replace(service.settings.processing, device="cpu"))
        latest = controller.status()
        self.assertNotEqual(original["check_id"], latest["check_id"])
        self.wait_for(lambda: controller.status()["status"] == "completed")
        self.assertFalse(controller.status()["capabilities"]["ready"])

    def test_failures_keep_only_bounded_timings_and_no_sensitive_exception_text(self):
        def probe(settings, progress, cancellation):
            for stage in STAGES:
                progress(stage, "started", 0)
                progress(stage, "completed", 123)
            raise RuntimeError("private transcript and C:/private/media.mkv")

        controller, _ = self.setup_check(probe)
        controller.start()
        self.wait_for(lambda: controller.status()["status"] == "failed")
        state = controller.status()
        self.assertLessEqual(len(state["timings"]), 9)
        self.assertIsNone(state["capabilities"])
        self.assertNotIn("private", json.dumps(state))
        state["timings"].clear()
        self.assertEqual(len(controller.status()["timings"]), 9)

    def test_close_signals_cancellation_and_rejects_new_checks(self):
        entered, stopped = Event(), Event()

        def probe(settings, progress, cancellation):
            entered.set()
            cancellation.wait(2)
            stopped.set()
            raise InterruptedError()

        controller, _ = self.setup_check(probe)
        controller.start()
        self.assertTrue(entered.wait(1))
        controller.close()
        self.assertTrue(stopped.wait(1))
        with self.assertRaisesRegex(RuntimeError, "closing"):
            controller.start()

    def test_worker_uses_private_interpreter_and_path_with_narrow_progress_protocol(self):
        settings = AppSettings.defaults()
        process = MagicMock()
        process.stdout = StringIO(json.dumps({"type": "progress", "stage": "device", "state": "completed", "duration_ms": 10}) + "\n"
                                  + json.dumps({"type": "result", "capabilities": {"ready": True}}) + "\n")
        process.poll.return_value = 0
        progress = MagicMock()
        with patch("backend.desktop.system_check.subprocess.Popen", return_value=process) as launch:
            self.assertTrue(run_check(settings, progress, Event())["ready"])
        self.assertEqual(launch.call_args.args[0][:2], [sys.executable, "-B"])
        self.assertEqual(launch.call_args.kwargs["stderr"], subprocess.DEVNULL)
        payload = json.loads(process.stdin.write.call_args.args[0])
        self.assertEqual(payload["sys_path"], sys.path)
        self.assertEqual(payload["settings"]["whisper"]["model"], "large-v3")
        progress.assert_called_once_with("device", "completed", 10)

    def test_stage_callback_records_failure_before_raising(self):
        progress = MagicMock()
        def fail():
            raise ValueError("driver")
        with self.assertRaises(ValueError):
            check_stage(progress, "device", fail)
        self.assertEqual(progress.call_args_list[0].args, ("device", "started", 0))
        self.assertEqual(progress.call_args_list[1].args[:2], ("device", "failed"))


if __name__ == "__main__":
    unittest.main()
