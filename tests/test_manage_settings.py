import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.jobs.batch import main as batch_main
from backend.settings import AppSettings, SettingsStore
from scripts.manage_settings import main


class ManageSettingsTests(unittest.TestCase):
    def test_set_options_updates_phase_6_preferences(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = SettingsStore(root / "settings.ini", AppSettings.defaults(root / "home"))

            exit_code = main(
                [
                    "set-options",
                    "--mode",
                    "report_only",
                    "--stereo-method",
                    "karaoke",
                    "--padding-before-ms",
                    "200",
                    "--padding-after-ms",
                    "75",
                    "--surround-output",
                    "downmix_stereo",
                    "--video-mode",
                    "preserve_source",
                    "--archive-after-success",
                ],
                store,
            )
            settings = store.load()

        self.assertEqual(exit_code, 0)
        self.assertEqual(settings.processing.mode, "report_only")
        self.assertEqual(settings.censoring.stereo_method, "karaoke")
        self.assertEqual(settings.censoring.padding_before_ms, 200)
        self.assertEqual(settings.censoring.padding_after_ms, 75)
        self.assertEqual(settings.audio.surround_output, "downmix_stereo")
        self.assertEqual(settings.video.mode, "preserve_source")
        self.assertTrue(settings.source.archive_after_success)

    def create_store(self, root: Path) -> SettingsStore:
        return SettingsStore(root / "app-data" / "settings.ini", AppSettings.defaults(root / "home"))

    def test_init_persists_defaults_and_creates_directories(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = self.create_store(root)

            exit_code = main(["init"], store)

            self.assertEqual(exit_code, 0)
            self.assertTrue(store.path.is_file())
            self.assertTrue(store.load().directories.input.is_dir())

    def test_set_directories_updates_selected_path_and_creates_it(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = self.create_store(root)
            custom_input = root / "custom" / "incoming"

            exit_code = main(
                ["set-directories", "--input", str(custom_input), "--create"],
                store,
            )

            self.assertEqual(exit_code, 0)
            self.assertEqual(store.load().directories.input, custom_input.resolve())
            self.assertTrue(custom_input.is_dir())

    def test_validate_returns_nonzero_for_missing_directories(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = self.create_store(Path(temporary_directory))

            with patch("sys.stdout", io.StringIO()):
                exit_code = main(["validate"], store)

            self.assertEqual(exit_code, 1)

    def test_batch_list_uses_persisted_directories(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = self.create_store(root)
            output = io.StringIO()

            with patch("sys.stdout", output):
                exit_code = batch_main(["--list"], store)

            self.assertEqual(exit_code, 0)
            self.assertIn(str(store.load().directories.input), output.getvalue())
            self.assertTrue(store.load().directories.input.is_dir())


if __name__ == "__main__":
    unittest.main()