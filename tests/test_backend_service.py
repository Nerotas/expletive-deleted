import tempfile
import unittest
from pathlib import Path

from backend.service import BackendService
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
        return SettingsStore(root / "settings.json", AppSettings(directories=directories))

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

            persisted = store.load()

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


if __name__ == "__main__":
    unittest.main()