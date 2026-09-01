import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.policy import PolicyStore, ProfanityPolicy
from backend.runtime import (
    DependencyStatus,
    get_profanity_censor_words_file,
    get_profanity_exclusions_file,
    load_profanity_censor_words,
    load_profanity_exclusions,
)
from scripts.desktop_bridge import DesktopBridge, serve


class DesktopBridgeTests(unittest.TestCase):
    @staticmethod
    def policy(
        root: Path,
        censor_words: set[str],
        exclusions: set[str],
    ) -> ProfanityPolicy:
        return ProfanityPolicy(
            censor_words=frozenset(censor_words),
            exclusions=frozenset(exclusions),
            censor_defaults_path=root / "words.txt",
            exclusions_defaults_path=root / "exclusions.txt",
            overrides_path=root / "policy.json",
            overrides_count=0,
        )

    def test_dictionary_inventory_seeds_complete_user_dictionary_from_defaults(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            dictionary_path = Path(temporary_directory) / "dictionary" / "profanity.json"
            with patch.dict("os.environ", {}, clear=True):
                policy_store = PolicyStore(dictionary_path)
                bridge = DesktopBridge(MagicMock(), policy_store)
                result = bridge.handle("dictionary.get")
                expected_words_path = get_profanity_censor_words_file()
                expected_exclusions_path = get_profanity_exclusions_file()

        self.assertEqual(Path(result["dictionary_path"]), dictionary_path)
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["seeded_from_default_version"], 1)
        self.assertEqual(set(result["words"]), load_profanity_censor_words(expected_words_path))
        self.assertEqual(
            set(result["exclusions"]),
            load_profanity_exclusions(expected_exclusions_path),
        )
        self.assertGreater(result["words_count"], 0)

    def test_dictionary_inventory_reports_backend_policy_counts(self):
        service = MagicMock()
        policy_store = MagicMock()
        policy_store.load.return_value = self.policy(
            Path("C:/policy"),
            {"one", "two"},
            {"allowed"},
        )
        bridge = DesktopBridge(service, policy_store)

        result = bridge.handle("dictionary.get")

        self.assertEqual(result["words_count"], 2)
        self.assertEqual(result["exclusions_count"], 1)
        self.assertEqual(result["dictionary_path"], str(Path("C:/policy/policy.json")))

    def test_dictionary_portability_methods_use_policy_store(self):
        service = MagicMock()
        policy_store = MagicMock()
        policy = self.policy(Path("C:/policy"), {"word"}, {"allowed"})
        policy_store.restore_defaults.return_value = policy
        policy_store.import_dictionary.return_value = policy
        policy_store.export_dictionary.return_value = Path("C:/backup/dictionary.json")
        bridge = DesktopBridge(service, policy_store)

        restored = bridge.handle("dictionary.restore_defaults")
        imported = bridge.handle("dictionary.import", {"source": "C:/backup/import.json"})
        exported = bridge.handle(
            "dictionary.export",
            {"destination": "C:/backup/dictionary.json"},
        )

        policy_store.restore_defaults.assert_called_once_with()
        policy_store.import_dictionary.assert_called_once_with(Path("C:/backup/import.json"))
        policy_store.export_dictionary.assert_called_once_with(Path("C:/backup/dictionary.json"))
        self.assertEqual(restored["words"], ["word"])
        self.assertEqual(imported["exclusions"], ["allowed"])
        self.assertEqual(exported, {"path": str(Path("C:/backup/dictionary.json"))})

    def test_dictionary_update_persists_through_policy_store(self):
        service = MagicMock()
        policy_store = MagicMock()
        updated = self.policy(Path("C:/policy"), {"new-word"}, set())
        policy_store.update.return_value = (updated, True)
        bridge = DesktopBridge(service, policy_store)

        result = bridge.handle(
            "dictionary.add",
            {"target": "censor", "word": "new-word"},
        )

        policy_store.update.assert_called_once_with("censor", "new-word", "add")
        self.assertTrue(result["changed"])
        self.assertEqual(result["words"], ["new-word"])

    def test_protocol_returns_library_and_correlates_request(self):
        service = MagicMock()
        item = MagicMock()
        item.to_dict.return_value = {"source": "C:/media/movie.mkv", "status": "ready"}
        service.get_library.return_value = (item,)
        request = io.StringIO('{"id":7,"method":"library.list"}\n')
        output = io.StringIO()

        exit_code = serve(DesktopBridge(service), request, output)

        response = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(response["id"], 7)
        self.assertTrue(response["ok"])
        self.assertEqual(response["result"][0]["status"], "ready")
        service.close.assert_called_once()

    def test_archive_and_import_methods_use_the_narrow_service_operations(self):
        service = MagicMock()
        archive_item = MagicMock()
        archive_item.to_dict.return_value = {"source": "C:/media/Processed/movie.mkv"}
        service.get_archive.return_value = (archive_item,)
        bridge = DesktopBridge(service)

        imported = bridge.handle("library.import", {"sources": ["C:/media/movie.mkv"]})
        archived = bridge.handle("archive.list")
        restored = bridge.handle("archive.restore", {"source": "C:/media/Processed/movie.mkv"})
        purged = bridge.handle("archive.purge", {"source": "C:/media/Processed/movie.mkv"})

        service.import_sources.assert_called_once_with([Path("C:/media/movie.mkv")])
        service.restore_archive_source.assert_called_once_with(Path("C:/media/Processed/movie.mkv"))
        service.purge_archive_source.assert_called_once_with(Path("C:/media/Processed/movie.mkv"))
        self.assertEqual(imported, service.import_sources.return_value)
        self.assertEqual(archived, [{"source": "C:/media/Processed/movie.mkv"}])
        self.assertEqual(restored, service.restore_archive_source.return_value)
        self.assertEqual(purged, service.purge_archive_source.return_value)

    def test_selective_batch_submission_preserves_ordered_results(self):
        service = MagicMock()
        queued = MagicMock()
        queued.to_dict.return_value = {
            "source": "C:/media/first.mkv",
            "status": "queued",
            "job": {"id": "job-1"},
        }
        rejected = MagicMock()
        rejected.to_dict.return_value = {
            "source": "C:/media/missing.mkv",
            "status": "rejected",
            "code": "unavailable",
            "detail": "Source file does not exist",
        }
        service.submit_jobs.return_value = (queued, rejected)
        bridge = DesktopBridge(service)

        result = bridge.handle(
            "jobs.submit_many",
            {
                "sources": ["C:/media/first.mkv", "C:/media/missing.mkv"],
                "mode": "report_only",
            },
        )

        service.submit_jobs.assert_called_once_with(
            [Path("C:/media/first.mkv"), Path("C:/media/missing.mkv")],
            "report_only",
        )
        self.assertEqual([item["status"] for item in result], ["queued", "rejected"])

    def test_single_job_submission_forwards_explicit_reprocessing_options(self):
        service = MagicMock()
        job = MagicMock()
        job.to_dict.return_value = {"id": "job-1", "mode": "censor"}
        service.submit_job.return_value = job
        bridge = DesktopBridge(service)

        result = bridge.handle(
            "jobs.submit",
            {
                "source": "C:/media/movie.mkv",
                "mode": "censor",
                "overwrite_output": True,
            },
        )

        service.submit_job.assert_called_once_with(
            Path("C:/media/movie.mkv"),
            "censor",
            force_transcribe=False,
            overwrite_output=True,
        )
        self.assertEqual(result["id"], "job-1")

    def test_review_list_reads_a_saved_transcript_and_excludes_classified_words(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "movie.mkv"
            transcript = root / "movie-transcript.json"
            transcript.write_text(
                json.dumps({"words": [{"word": "weirdo", "start": 3.0, "end": 3.4}]}),
                encoding="utf-8",
            )
            service = MagicMock()
            service.settings.directories.transcripts = root
            policy_store = MagicMock()
            policy_store.load.return_value = self.policy(root, {"fuck"}, set())
            bridge = DesktopBridge(service, policy_store)

            result = bridge.handle("reviews.list", {"source": str(source)})

        self.assertEqual(result["candidates"], [{"word": "weirdo", "start": 3.0, "end": 3.4}])

    def test_dictionary_inventory_includes_unique_unclassified_discovered_words(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "one-transcript.json").write_text(
                json.dumps({"words": [{"word": "weirdo"}, {"word": "jerk"}]}),
                encoding="utf-8",
            )
            (root / "two-transcript.json").write_text(
                json.dumps({"words": [{"word": "weirdo"}]}),
                encoding="utf-8",
            )
            service = MagicMock()
            service.settings.directories.transcripts = root
            policy_store = MagicMock()
            policy_store.load.return_value = self.policy(root, {"jerk"}, set())
            bridge = DesktopBridge(service, policy_store)

            with patch(
                "scripts.desktop_bridge.find_review_candidates",
                side_effect=lambda payload, censor, _exclude: [
                    {"word": item["word"]}
                    for item in payload["words"]
                    if item["word"] not in censor
                ],
            ):
                result = bridge.handle("dictionary.get")

        self.assertEqual(result["discovered_count"], 1)
        self.assertEqual(result["discovered"], ["weirdo"])

    def test_protocol_returns_structured_error(self):
        service = MagicMock()
        request = io.StringIO('{"id":8,"method":"not.real"}\n')
        output = io.StringIO()

        serve(DesktopBridge(service), request, output)

        response = json.loads(output.getvalue())
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["type"], "ValueError")
        self.assertIn("Unknown desktop bridge method", response["error"]["message"])

    def test_ffmpeg_location_validates_companion_and_persists_both_paths(self):
        service = MagicMock()
        service.get_settings.return_value = {
            "runtime": {
                "ffmpeg_path": None,
                "ffprobe_path": None,
                "whisper_cache": None,
            }
        }
        service.get_capabilities.return_value = {"ready": True}
        ready = lambda dependency_id, name, path: DependencyStatus(
            id=dependency_id,
            name=name,
            state="ready",
            required_version="8.0 or later",
            installed_version="8.0",
            path=Path(path),
            detail="ready",
            install_supported=True,
        )
        bridge = DesktopBridge(service)

        with patch(
            "scripts.desktop_bridge.inspect_executable",
            side_effect=[
                ready("ffmpeg", "FFmpeg", "C:/Tools/ffmpeg.exe"),
                ready("ffprobe", "FFprobe", "C:/Tools/ffprobe.exe"),
            ],
        ):
            result = bridge.handle(
                "dependencies.locate_ffmpeg",
                {"path": "C:/Tools/ffmpeg.exe"},
            )

        updated = service.update_settings.call_args.args[0]
        self.assertEqual(updated["runtime"]["ffmpeg_path"], str(Path("C:/Tools/ffmpeg.exe").resolve()))
        self.assertEqual(updated["runtime"]["ffprobe_path"], str(Path("C:/Tools/ffprobe.exe").resolve()))
        self.assertEqual(result, {"ready": True})

    def test_dependency_plan_discloses_managed_destination_without_installing(self):
        service = MagicMock()
        service.settings.runtime.whisper_cache = None
        service.settings.whisper.library = "faster-whisper"
        service.settings.whisper.model = "large-v3"
        bridge = DesktopBridge(service)

        with patch.dict(
            "os.environ",
            {"CENSOR_RUNTIME_ASSETS_DIR": "/tmp/expletive-runtime"},
            clear=False,
        ):
            result = bridge.handle("dependencies.plan", {"components": ["whisper_model"]})

        self.assertEqual(
            result["actions"][0]["destination"],
            str((Path("/tmp/expletive-runtime") / "models" / "whisper").resolve()),
        )
        service.update_settings.assert_not_called()


if __name__ == "__main__":
    unittest.main()
