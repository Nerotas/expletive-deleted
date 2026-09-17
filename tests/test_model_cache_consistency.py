"""Exercise readiness and job loading against the same offline cache fixtures."""

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.censor.engine import ProfanityCensor
from backend.jobs import JobManager
from backend.jobs.batch import main as batch_main
from backend.runtime.dependencies import (
    DependencyStatus,
    WHISPER_MODEL_FILES,
    WHISPER_MODEL_ID,
    WHISPER_MODEL_REVISION,
)
from backend.service.capabilities import get_capabilities
from backend.settings import AppSettings, ensure_directories


class ModelLookupCensor(ProfanityCensor):
    def process(self, **options):
        # Keep real engine initialization and model loading, replacing only media work.
        self._load_whisper_model()
        transcript = Path(self.get_transcript_path())
        transcript.parent.mkdir(parents=True, exist_ok=True)
        transcript.write_text("{}")
        return True


class ModelCacheConsistencyTests(unittest.TestCase):
    def cache_model(self, cache):
        snapshot = cache / ("models--" + WHISPER_MODEL_ID.replace("/", "--")) / "snapshots" / WHISPER_MODEL_REVISION
        snapshot.mkdir(parents=True)
        for name in WHISPER_MODEL_FILES:
            (snapshot / name).write_text("offline lookup fixture, not model weights")
        return snapshot

    def test_system_check_and_jobs_agree_on_model_location(self):
        cases = (
            ("managed default", False, True, False, True),
            ("custom location", True, False, True, True),
            ("missing custom does not fall back", True, True, False, False),
            ("missing managed", False, False, False, False),
        )
        for name, custom, managed_exists, custom_exists, expected_ready in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                managed = root / "runtime" / "models" / "whisper"
                configured = root / "custom" if custom else None
                if managed_exists:
                    self.cache_model(managed)
                if custom_exists:
                    self.cache_model(configured)
                settings = AppSettings.defaults(root / "media")
                settings = replace(settings, runtime=replace(settings.runtime, whisper_cache=configured))
                ensure_directories(settings.directories)
                source = settings.directories.input / "movie.mkv"
                source.write_bytes(b"original media")
                ready = DependencyStatus("test", "test", "ready", None, None, None, "stub", False)
                device = MagicMock(selected="cpu", compute_type="int8", detail="test")
                policy = MagicMock()
                policy.load.return_value.censor_words = set()
                policy.load.return_value.exclusions = set()
                from faster_whisper.utils import download_model

                with (
                    patch.dict("os.environ", {
                        "CENSOR_RUNTIME_ASSETS_DIR": str(root / "runtime"),
                        "CENSOR_PROJECT_ROOT": str(root / "legacy"),
                        "CENSOR_WHISPER_CACHE_DIR": str(root / "legacy-cache"),
                        "HF_HUB_OFFLINE": "1",
                    }),
                    patch("backend.runtime.dependency_inspection.inspect_executable", return_value=ready),
                    patch("backend.runtime.dependency_inspection.inspect_python_dependencies", return_value=(ready,)),
                    patch("backend.runtime.dependency_inspection.inspect_ytdlp", return_value=ready),
                    patch("backend.runtime.dependency_inspection.inspect_js_runtime", return_value=ready),
                    patch("backend.service.capabilities.get_whisper_device_status", return_value=device),
                    patch("backend.censor.engine.get_whisper_device_status", return_value=device),
                    patch("backend.runtime.transcription.get_whisper_device_status", return_value=device),
                    patch("backend.runtime.locations.find_ffmpeg", return_value="ffmpeg"),
                    patch("backend.runtime.locations.find_ffprobe", return_value="ffprobe"),
                    patch("backend.censor.engine.PolicyStore", return_value=policy),
                    patch("faster_whisper.utils.download_model", wraps=download_model) as lookup,
                    patch("faster_whisper.WhisperModel") as model,
                ):
                    capabilities = get_capabilities(settings)
                    manager = JobManager(settings, censor_factory=ModelLookupCensor)
                    try:
                        job = manager.submit(source, "report_only")
                        completed = manager.wait(job.id, timeout=5)
                    finally:
                        manager.close()

                self.assertEqual(capabilities["processing_ready"], expected_ready)
                self.assertEqual(completed.status, "transcribed" if expected_ready else "failed")
                self.assertEqual(source.read_bytes(), b"original media")
                self.assertFalse(any(settings.directories.output.iterdir()))
                self.assertEqual(len(lookup.call_args_list), 2)
                for call in lookup.call_args_list:
                    self.assertEqual(Path(call.kwargs["cache_dir"]), (configured or managed).resolve())
                    self.assertTrue(call.kwargs["local_files_only"])
                    self.assertEqual(call.kwargs["revision"], WHISPER_MODEL_REVISION)
                if expected_ready:
                    self.assertEqual(model.call_args.args[0], capabilities["model_path"])
                    self.assertTrue(model.call_args.kwargs["local_files_only"])
                else:
                    model.assert_not_called()
                    self.assertIn("not prepared", completed.error.detail)

    def test_settings_driven_batch_passes_same_cache_to_model_and_engine(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = AppSettings.defaults(root / "media")
            ensure_directories(settings.directories)
            (settings.directories.input / "movie.mkv").write_bytes(b"original")
            for configured in (None, root / "custom"):
                with (
                    self.subTest(configured=configured),
                    patch.dict("os.environ", {"CENSOR_RUNTIME_ASSETS_DIR": str(root / "runtime")}),
                    patch("backend.jobs.batch.load_effective_settings", return_value=replace(
                        settings, runtime=replace(settings.runtime, whisper_cache=configured)
                    )),
                    patch("backend.jobs.batch.find_ffprobe", return_value=None),
                    patch("backend.jobs.batch.load_whisper_model") as load,
                    patch("backend.jobs.batch.process_file", return_value=("ok", set(), False, 0)) as process,
                ):
                    self.assertEqual(batch_main(["--report-only"]), 0)
                    expected = (configured or root / "runtime" / "models" / "whisper").resolve()
                    self.assertEqual(load.call_args.args[2], expected)
                    self.assertEqual(process.call_args.kwargs["whisper_cache_dir"], expected)
