import tempfile
import unittest
from pathlib import Path

from backend.jobs import JobRecord
from backend.service import ArchiveSourceError, BackendService, ServiceBusyError
from backend.settings import AppSettings, DirectorySettings, SettingsStore


class StubManager:
    def __init__(self, settings):
        self.settings = settings
        self.closed = False

    def list(self):
        return ()

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
            service = BackendService(self.create_store(root), manager_factory=StubManager)
            original = root / "outside" / "movie.mkv"
            original.parent.mkdir()
            original.write_bytes(b"original")
            try:
                result = service.import_sources([original])
                duplicate = service.import_sources([original])
            finally:
                service.close()

            copied = root / "Ready" / "movie.mkv"
            self.assertEqual(copied.read_bytes(), b"original")
            self.assertEqual(original.read_bytes(), b"original")
            self.assertEqual(result[0]["status"], "added")
            self.assertEqual(duplicate[0]["status"], "already_exists")

    def test_import_remains_available_while_a_job_is_processing(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            service = BackendService(self.create_store(root), manager_factory=StubManager)
            active_source = service.settings.directories.input / "active.mkv"
            active_source.write_bytes(b"active")
            service.jobs.list = lambda: (
                JobRecord("active-job", active_source, "censor", "transcribing", 25.0),
            )
            original = root / "outside" / "new.mkv"
            original.parent.mkdir()
            original.write_bytes(b"new")
            try:
                result = service.import_sources([original])
                copied = (root / "Ready" / "new.mkv").read_bytes()
            finally:
                service.close()

        self.assertEqual(result[0]["status"], "added")
        self.assertEqual(copied, b"new")

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

    def test_archive_requires_idle_queue_and_never_overwrites_destination(self):
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


if __name__ == "__main__":
    unittest.main()
