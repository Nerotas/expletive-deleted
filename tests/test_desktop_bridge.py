import io
import json
import tempfile
import unittest
from pathlib import Path
from threading import Event
from time import perf_counter
from unittest.mock import MagicMock, patch

from backend.policy import PolicyEntry, PolicyStore, ProfanityPolicy
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
            dictionary_path=root,
            censor_entries={
                word: PolicyEntry(word, "1970-01-01T00:00:00Z", "default")
                for word in censor_words
            },
            exclusion_entries={
                word: PolicyEntry(word, "2026-09-01T12:00:00Z", "user")
                for word in exclusions
            },
        )

    def test_dictionary_inventory_seeds_complete_user_dictionary_from_defaults(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            dictionary_path = Path(temporary_directory) / "dictionary"
            with patch.dict("os.environ", {}, clear=True):
                policy_store = PolicyStore(dictionary_path)
                bridge = DesktopBridge(MagicMock(), policy_store)
                info = bridge.handle("dictionary.info")
                exclusions = bridge.handle("dictionary.exclusions", {"page_size": 100})
                censored = bridge.handle("dictionary.censored", {"page_size": 100})
                expected_words_path = get_profanity_censor_words_file()
                expected_exclusions_path = get_profanity_exclusions_file()

        self.assertEqual(Path(info["dictionary_path"]), dictionary_path.resolve())
        self.assertEqual(info["schema_version"], 2)
        self.assertEqual(info["seeded_from_default_version"], 1)
        self.assertEqual(
            {entry["value"] for entry in exclusions["items"]},
            load_profanity_exclusions(expected_exclusions_path),
        )
        self.assertEqual(censored["target"], "censor")
        self.assertGreater(censored["total"], 0)

    def test_removed_dictionary_compatibility_operations_are_not_available(self):
        bridge = DesktopBridge(MagicMock(), MagicMock())

        for method in ("dictionary.get", "dictionary.summary", "dictionary.entries"):
            with self.subTest(method=method), self.assertRaisesRegex(
                ValueError,
                "Unknown desktop bridge method",
            ):
                bridge.handle(method)

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
        self.assertEqual(restored["words_count"], 1)
        self.assertEqual(imported["exclusions_count"], 1)
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
        self.assertEqual(result["words_count"], 1)

    def test_dictionary_exclusions_are_fetched_without_loading_censored_words(self):
        service = MagicMock()
        policy_store = MagicMock()
        policy_store.load_entries.return_value = (
            PolicyEntry("allowed-z", "2026-09-01T12:00:00Z", "user"),
            PolicyEntry("allowed-a", "2026-09-01T12:00:00Z", "user"),
            PolicyEntry("other", "2026-09-01T12:00:00Z", "user"),
        )
        bridge = DesktopBridge(service, policy_store)

        result = bridge.handle("dictionary.exclusions", {
            "page": 1,
            "page_size": 10,
            "sort": "value",
            "direction": "desc",
            "search": "allowed",
        })

        self.assertEqual([item["value"] for item in result["items"]], ["allowed-z", "allowed-a"])
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["total_pages"], 1)
        self.assertEqual(result["items"][0]["source"], "user")
        policy_store.load_entries.assert_called_once_with("exclude")
        policy_store.load.assert_not_called()

    def test_dictionary_censored_words_use_their_own_operation(self):
        policy_store = MagicMock()
        policy_store.load_entries.return_value = (
            PolicyEntry("blocked", "1970-01-01T00:00:00Z", "default"),
        )
        bridge = DesktopBridge(MagicMock(), policy_store)

        result = bridge.handle("dictionary.censored", {"page_size": 10})

        self.assertEqual(result["target"], "censor")
        self.assertEqual(result["items"][0]["value"], "blocked")
        policy_store.load_entries.assert_called_once_with("censor")

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

    def test_blocked_queue_request_does_not_delay_dictionary_request(self):
        release_queue = Event()
        bridge = MagicMock()

        def handle(method, _params=None):
            if method == "library.list":
                release_queue.wait(timeout=2)
                return []
            release_queue.set()
            return {"dictionary_path": "C:/dictionary"}

        bridge.handle.side_effect = handle
        requests = io.StringIO(
            '{"id":1,"method":"library.list"}\n'
            '{"id":2,"method":"dictionary.info"}\n'
        )
        output = io.StringIO()

        started = perf_counter()
        serve(bridge, requests, output)
        elapsed = perf_counter() - started

        responses = {item["id"]: item for item in map(json.loads, output.getvalue().splitlines())}
        self.assertLess(elapsed, 1)
        self.assertEqual(responses[2]["result"]["dictionary_path"], "C:/dictionary")
        bridge.close.assert_called_once_with()

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

    def test_review_list_returns_discovered_and_configured_censored_words(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "movie.mkv"
            transcript = root / "movie-transcript.json"
            transcript.write_text(
                json.dumps({"words": [
                    {"word": "weirdo", "start": 3.0, "end": 3.4},
                    {"word": "fuck", "start": 4.0, "end": 4.4},
                ]}),
                encoding="utf-8",
            )
            service = MagicMock()
            service.settings.directories.transcripts = root
            policy_store = MagicMock()
            policy_store.load.return_value = self.policy(root, {"fuck"}, set())
            bridge = DesktopBridge(service, policy_store)

            result = bridge.handle("reviews.list", {"source": str(source)})

        self.assertEqual(result["candidates"], [{"word": "weirdo", "start": 3.0, "end": 3.4}])
        self.assertEqual(result["censored"], [{"word": "fuck", "start": 4.0, "end": 4.4}])

    def test_dictionary_discovered_reads_only_its_own_store(self):
        policy_store = MagicMock()
        policy_store.load_discovered.return_value = ("oddity", "weirdo")
        bridge = DesktopBridge(MagicMock(), policy_store)

        result = bridge.handle("dictionary.discovered")

        policy_store.initialize_discovered.assert_called_once_with()
        policy_store.load_discovered.assert_called_once_with()
        policy_store.load.assert_not_called()
        self.assertEqual(result["words"], ["oddity", "weirdo"])

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

        model_action = next(
            action for action in result["actions"] if action["id"].startswith("download-")
        )

        self.assertEqual(
            model_action["destination"],
            str((Path("/tmp/expletive-runtime") / "models" / "whisper").resolve()),
        )
        service.update_settings.assert_not_called()


if __name__ == "__main__":
    unittest.main()
