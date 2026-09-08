import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from unittest.mock import MagicMock, patch

from backend.jobs import JobManager, JobRecord
from backend.jobs.models import JobError
from backend.service import ArchiveSourceError, BackendService, LibraryItem, ServiceBusyError
from backend.service.capabilities import get_capabilities
from backend.settings import AppSettings, DirectorySettings, SettingsStore


class StubManager:
    def __init__(self, settings):
        self.settings = settings
        self.closed = False
        self._jobs = ()

    def list(self):
        return self._jobs

    def wait(self, job_id, timeout=None):
        return None

    def close(self):
        self.closed = True


class BackendServiceTests(unittest.TestCase):
    def create_store(self, root: Path) -> SettingsStore:
        directories = DirectorySettings(
            input=root / "Ready",
            output=root / "Finished",
            archive=root / "Processed",
            transcripts=root / "Transcripts",
        )
        return SettingsStore(root / "settings.ini", AppSettings(directories=directories))

    def test_settings_update_is_persisted_and_rebuilds_manager(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = self.create_store(Path(temporary_directory))
            managers = []

            def manager_factory(settings):
                manager = StubManager(settings)
                managers.append(manager)
                return manager

            service = BackendService(store, manager_factory=manager_factory)
            payload = service.get_settings()
            payload["processing"]["mode"] = "report_only"
            updated = service.update_settings(payload)
            service.close()

            reopened = BackendService(store, manager_factory=StubManager)
            persisted = reopened.settings
            reopened.close()

        self.assertEqual(updated["processing"]["mode"], "report_only")
        self.assertEqual(persisted.processing.mode, "report_only")
        self.assertTrue(managers[0].closed)
        self.assertTrue(managers[1].closed)

    def test_completed_youtube_download_queues_transcript_first_automation(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            service = BackendService(
                self.create_store(Path(temporary_directory)),
                manager_factory=StubManager,
            )
            submit = MagicMock()
            service.jobs.submit = submit
            source = service.settings.directories.input / "downloaded-video.mp4"
            try:
                service._queue_completed_youtube_download(source)
            finally:
                service.close()

        submit.assert_called_once_with(source, "report_only", auto_censor_after_transcription=True)

    def test_capabilities_without_configured_cache_inspect_managed_cache(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            service = BackendService(
                self.create_store(Path(temporary_directory)),
                manager_factory=StubManager,
            )
            managed_cache = Path(temporary_directory) / "models" / "whisper"
            try:
                with (
                    patch(
                        "backend.service.capabilities.get_managed_whisper_cache_dir",
                        return_value=managed_cache,
                    ),
                    patch(
                        "backend.service.capabilities.inspect_dependencies",
                        side_effect=RuntimeError("inspection stopped"),
                    ) as inspect,
                    self.assertRaisesRegex(RuntimeError, "inspection stopped"),
                ):
                    get_capabilities(service.settings)
            finally:
                service.close()

        self.assertEqual(inspect.call_args.args[0], managed_cache)

    def test_library_uses_configured_directories(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = self.create_store(Path(temporary_directory))
            service = BackendService(store, manager_factory=StubManager)
            source = service.settings.directories.input / "movie.mkv"
            source.write_bytes(b"source")
            try:
                items = service.get_library()
            finally:
                service.close()

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].source.name, "movie.mkv")

    def test_import_copies_supported_source_without_overwriting_or_touching_original(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            service = BackendService(self.create_store(root), manager_factory=JobManager)
            original = root / "outside" / "movie.mkv"
            original.parent.mkdir()
            original.write_bytes(b"original")
            try:
                result = service.import_sources([original])
                queued_job = next(job for job in service.jobs.list() if job.source == original.resolve())
                completed = service.jobs.wait(queued_job.id, timeout=2)
                duplicate = service.import_sources([original])
            finally:
                service.close()

            copied = root / "Ready" / "movie.mkv"
            self.assertEqual(copied.read_bytes(), b"original")
            self.assertEqual(original.read_bytes(), b"original")
            self.assertEqual(result[0]["status"], "added")
            self.assertEqual(queued_job.mode, "copy")
            self.assertEqual(completed.status, "completed")
            self.assertEqual(duplicate[0]["status"], "already_exists")

    def test_import_remains_available_while_a_job_is_processing(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            service = BackendService(self.create_store(root), manager_factory=JobManager)
            active_source = service.settings.directories.input / "active.mkv"
            active_source.write_bytes(b"active")
            service.jobs._jobs["active-job"] = JobRecord("active-job", active_source, "censor", "transcribing", 25.0)
            service.jobs._events["active-job"] = []
            service.jobs._cancellations["active-job"] = Event()
            service.jobs._futures["active-job"] = MagicMock()
            original = root / "outside" / "new.mkv"
            original.parent.mkdir()
            original.write_bytes(b"new")
            try:
                result = service.import_sources([original])
                queued_job = next(job for job in service.jobs.list() if job.source == original.resolve())
                completed = service.jobs.wait(queued_job.id, timeout=2)
                copied = (root / "Ready" / "new.mkv").read_bytes()
            finally:
                service.close()

        self.assertEqual(result[0]["status"], "added")
        self.assertEqual(completed.status, "completed")
        self.assertEqual(copied, b"new")

    def test_import_creates_background_copy_job_and_completes_into_ready(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            service = BackendService(self.create_store(root), manager_factory=JobManager)
            original = root / "outside" / "movie.mkv"
            original.parent.mkdir()
            original.write_bytes(b"queued-copy")
            try:
                result = service.import_sources([original])
                queued_job = next(job for job in service.jobs.list() if job.source == original.resolve())
                completed = service.jobs.wait(queued_job.id, timeout=2)
                copied = (root / "Ready" / "movie.mkv").read_bytes()
            finally:
                service.close()

        self.assertEqual(result[0]["status"], "added")
        self.assertEqual(queued_job.mode, "copy")
        self.assertEqual(completed.status, "completed")
        self.assertEqual(copied, b"queued-copy")

    def test_archive_lists_and_purges_only_its_own_supported_files(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            service = BackendService(self.create_store(root), manager_factory=StubManager)
            archived = root / "Processed" / "nested" / "movie.mkv"
            archived.parent.mkdir()
            archived.write_bytes(b"original")
            (root / "Processed" / "notes.txt").write_text("keep", encoding="utf-8")
            try:
                items = service.get_archive()
                result = service.purge_archive_source(archived)
            finally:
                service.close()

            self.assertEqual(items[0].relative_path, Path("nested/movie.mkv"))
            self.assertEqual(result["deleted_bytes"], len(b"original"))
            self.assertFalse(archived.exists())
            self.assertTrue((root / "Processed" / "notes.txt").is_file())

    def test_archive_blocks_own_job_and_never_overwrites_destination(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            service = BackendService(self.create_store(root), manager_factory=StubManager)
            source = service.settings.directories.input / "movie.mkv"
            source.write_bytes(b"source")
            output = service.settings.directories.output / "movie-censored.mkv"
            output.write_bytes(b"output")
            active = JobRecord("active-job", source, "censor", "transcribing", 25.0)
            service.jobs.list = lambda: (active,)
            try:
                with self.assertRaises(ServiceBusyError):
                    service.archive_source(source)

                service.jobs.list = lambda: ()
                destination = service.settings.directories.archive / "movie.mkv"
                destination.write_bytes(b"existing")
                with self.assertRaisesRegex(ArchiveSourceError, "already exists"):
                    service.archive_source(source)
            finally:
                service.close()

            self.assertEqual(source.read_bytes(), b"source")
            self.assertEqual(destination.read_bytes(), b"existing")

    def test_archive_lock_is_per_source_for_all_job_states(self):
        for library_status in ("finished", "transcribed"):
            for job_status in ("queued", "copying", "transcribing", "censoring", "verifying", "awaiting_review", "completed", "transcribed", "failed", "cancelled"):
                for same_source in (False, True):
                    with self.subTest(library_status=library_status, job_status=job_status, same_source=same_source), tempfile.TemporaryDirectory() as temporary_directory:
                        root = Path(temporary_directory)
                        service = BackendService(self.create_store(root), manager_factory=StubManager)
                        source = service.settings.directories.input / "movie.mkv"
                        source.write_bytes(b"original")
                        other = service.settings.directories.input / "other.mkv"
                        other.write_bytes(b"other original")
                        artifact = (service.settings.directories.output / "movie-censored.mkv"
                                    if library_status == "finished" else
                                    service.settings.directories.transcripts / "movie-transcript.json")
                        artifact.write_bytes(b"{}")
                        # Resolve equivalent paths before comparing source identity.
                        job_source = source.parent / "nested" / ".." / source.name if same_source else other
                        job = JobRecord("job", job_source, "censor", job_status, 25.0,
                                        error=JobError("processing_failed", "Failed") if job_status == "failed" else None)
                        service.jobs._jobs = (job,)
                        destination = service.settings.directories.archive / source.name
                        library_item = LibraryItem(
                            source,
                            library_status,
                            datetime.now(timezone.utc),
                            transcript=artifact if library_status == "transcribed" else None,
                            output=artifact if library_status == "finished" else None,
                        )
                        try:
                            with patch.object(service, "get_library", return_value=(library_item,)):
                                if same_source and job_status not in ("completed", "transcribed", "failed", "cancelled"):
                                    with self.assertRaisesRegex(ServiceBusyError, "This file.*queued or processing"):
                                        service.archive_source(source)
                                    self.assertEqual(source.read_bytes(), b"original")
                                    self.assertFalse(destination.exists())
                                else:
                                    result = service.archive_source(source)
                                    self.assertEqual(result["archived_to"], str(destination))
                                    self.assertFalse(source.exists())
                                    self.assertEqual(destination.read_bytes(), b"original")
                            self.assertEqual(service.jobs.list(), (job,))
                            self.assertEqual(other.read_bytes(), b"other original")
                            self.assertEqual(artifact.read_bytes(), b"{}")
                        finally:
                            service.close()

    def test_restore_archive_moves_file_back_to_ready_without_overwriting(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            service = BackendService(self.create_store(root), manager_factory=StubManager)
            archived = root / "Processed" / "nested" / "movie.mkv"
            archived.parent.mkdir()
            archived.write_bytes(b"original")
            destination = root / "Ready" / "nested" / "movie.mkv"
            output = root / "Finished" / "nested" / "movie-censored.mkv"
            output.parent.mkdir()
            output.write_bytes(b"censored")
            try:
                service.jobs.list = lambda: (
                    JobRecord("active-job", destination, "censor", "transcribing", 25.0),
                )
                with self.assertRaises(ServiceBusyError):
                    service.restore_archive_source(archived)

                service.jobs.list = lambda: ()
                result = service.restore_archive_source(archived)
                self.assertEqual(Path(result["restored_to"]), destination.resolve())
                self.assertEqual(destination.read_bytes(), b"original")
                self.assertFalse(archived.exists())
                self.assertFalse(archived.parent.exists())
                self.assertEqual(service.get_library()[0].status, "finished")

                archived.parent.mkdir()
                archived.write_bytes(b"archived")
                with self.assertRaisesRegex(ArchiveSourceError, "already exists"):
                    service.restore_archive_source(archived)
            finally:
                service.close()

            self.assertEqual(archived.read_bytes(), b"archived")
            self.assertEqual(destination.read_bytes(), b"original")


if __name__ == "__main__":
    unittest.main()
