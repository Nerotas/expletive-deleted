import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from backend.application_identity import (
    APP_DATA_DIRECTORY_NAME,
    DISPLAY_NAME,
    prepare_app_data_root,
)
from backend.settings import (
    SETTINGS_SCHEMA_VERSION,
    AppSettings,
    DirectoryAccessError,
    DirectorySettings,
    SettingsFileError,
    SettingsStore,
    SettingsValidationError,
    default_app_data_root,
    ensure_directories,
    inspect_directories,
    load_effective_settings,
    resolve_runtime_paths,
    settings_from_dict,
    settings_to_dict,
)


class SettingsModelTests(unittest.TestCase):
    def test_defaults_use_user_documents_directories(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            home = Path(temporary_directory)
            settings = AppSettings.defaults(home)

        root = (home / "Documents" / "Expletive Deleted").resolve()
        self.assertEqual(settings.directories.input, root / "Ready")
        self.assertEqual(settings.directories.output, root / "Finished")
        self.assertEqual(settings.directories.archive, root / "Processed")
        self.assertEqual(settings.directories.transcripts, root / "Transcripts")
        settings.validate()

    def test_independent_directories_convert_to_runtime_paths(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            directories = DirectorySettings(
                input=(root / "incoming").resolve(),
                output=(root / "elsewhere" / "finished").resolve(),
                archive=(root / "archive" / "sources").resolve(),
                transcripts=(root / "reports").resolve(),
            )

            paths = directories.to_runtime_paths()

        self.assertEqual(paths.ready, directories.input)
        self.assertEqual(paths.finished, directories.output)
        self.assertEqual(paths.processed, directories.archive)
        self.assertEqual(paths.transcripts, directories.transcripts)

    def test_duplicate_directories_are_rejected(self):
        settings = AppSettings.defaults()
        duplicate = replace(
            settings,
            directories=replace(
                settings.directories,
                output=settings.directories.input,
            ),
        )

        with self.assertRaisesRegex(SettingsValidationError, "directories.output must differ"):
            duplicate.validate()

    def test_non_path_directory_value_is_rejected_cleanly(self):
        settings = AppSettings.defaults()
        invalid = replace(
            settings,
            directories=replace(settings.directories, input="not-a-path"),
        )

        with self.assertRaisesRegex(SettingsValidationError, "directories.input must be a path"):
            invalid.validate()

    def test_runtime_paths_are_optional_and_round_trip(self):
        settings = AppSettings.defaults()
        runtime = replace(
            settings.runtime,
            ffmpeg_path=Path("C:\\tools\\ffmpeg.exe"),
            ffprobe_path=Path("C:\\tools\\ffprobe.exe"),
            whisper_cache=Path("C:\\models"),
        )
        configured = replace(settings, runtime=runtime)

        restored = settings_from_dict(settings_to_dict(configured))

        self.assertEqual(restored.runtime, runtime)

    def test_old_schema_one_document_without_runtime_group_still_loads(self):
        payload = settings_to_dict(AppSettings.defaults())
        del payload["runtime"]

        restored = settings_from_dict(payload)

        self.assertIsNone(restored.runtime.ffmpeg_path)
        self.assertIsNone(restored.runtime.whisper_cache)

    def test_settings_round_trip_all_schema_groups(self):
        settings = AppSettings.defaults()

        payload = settings_to_dict(settings)
        restored = settings_from_dict(payload)

        self.assertEqual(payload["schema_version"], SETTINGS_SCHEMA_VERSION)
        self.assertEqual(restored, settings)

    def test_onboarding_defaults_incomplete_and_round_trips(self):
        settings = AppSettings.defaults()
        completed = replace(settings, onboarding=replace(settings.onboarding, completed=True))

        self.assertFalse(settings.onboarding.completed)
        self.assertTrue(settings_from_dict(settings_to_dict(completed)).onboarding.completed)

    def test_invalid_onboarding_value_is_rejected(self):
        payload = settings_to_dict(AppSettings.defaults())
        payload["onboarding"] = {"completed": "yes"}

        with self.assertRaisesRegex(SettingsValidationError, "onboarding.completed must be a boolean"):
            settings_from_dict(payload)

    def test_unknown_fields_are_rejected(self):
        payload = settings_to_dict(AppSettings.defaults())
        payload["mystery"] = True

        with self.assertRaisesRegex(SettingsValidationError, "unknown field"):
            settings_from_dict(payload)

    def test_unsupported_schema_version_is_rejected(self):
        payload = settings_to_dict(AppSettings.defaults())
        payload["schema_version"] = 99

        with self.assertRaisesRegex(SettingsValidationError, "unsupported"):
            settings_from_dict(payload)


class SettingsStoreTests(unittest.TestCase):
    def test_windows_app_data_default(self):
        root = default_app_data_root({"LOCALAPPDATA": "C:\\Users\\User\\AppData\\Local"})
        self.assertEqual(root, Path("C:\\Users\\User\\AppData\\Local\\ExpletiveDeleted"))

    def test_app_data_requires_local_app_data(self):
        with self.assertRaisesRegex(RuntimeError, "LOCALAPPDATA is required"):
            default_app_data_root({})

    def test_product_identity_uses_expletive_deleted_names(self):
        self.assertEqual(DISPLAY_NAME, "Expletive Deleted")
        self.assertEqual(APP_DATA_DIRECTORY_NAME, "ExpletiveDeleted")

    def test_prepare_app_data_root_resolves_fresh_state_without_creating_it(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            local_app_data = Path(temporary_directory)

            root = prepare_app_data_root({"LOCALAPPDATA": str(local_app_data)})

            self.assertEqual(root, (local_app_data / "ExpletiveDeleted").resolve())
            self.assertFalse(root.exists())

    def test_prepare_app_data_root_leaves_existing_canonical_state_untouched(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            local_app_data = Path(temporary_directory)
            canonical_root = local_app_data / "ExpletiveDeleted"
            canonical_root.mkdir()
            settings_path = canonical_root / "settings.ini"
            settings_path.write_text("current", encoding="utf-8")

            root = prepare_app_data_root({"LOCALAPPDATA": str(local_app_data)})

            self.assertEqual(root, canonical_root.resolve())
            self.assertEqual(settings_path.read_text(encoding="utf-8"), "current")

    def test_missing_file_initializes_an_ignored_ini_template(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "settings.ini"
            defaults = AppSettings.defaults(Path(temporary_directory))
            store = SettingsStore(path, defaults)

            loaded = store.load()

            self.assertEqual(loaded, defaults)
            self.assertTrue(path.exists())
            self.assertIn("[settings]", path.read_text(encoding="utf-8"))
            self.assertIn("[directories]", path.read_text(encoding="utf-8"))
            self.assertIn("[onboarding]", path.read_text(encoding="utf-8"))
            self.assertFalse(loaded.onboarding.completed)

    def test_save_and_load_round_trip_atomically(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "nested" / "settings.ini"
            settings = AppSettings.defaults(Path(temporary_directory))
            store = SettingsStore(path, settings)

            saved_path = store.save(settings)
            loaded = store.load()

            self.assertEqual(saved_path, path.resolve())
            self.assertEqual(loaded, settings)
            self.assertIn(f"schema_version = {SETTINGS_SCHEMA_VERSION}", path.read_text(encoding="utf-8"))
            self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_save_failure_preserves_existing_ini(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "settings.ini"
            settings = AppSettings.defaults(Path(temporary_directory))
            store = SettingsStore(path, settings)
            store.save(settings)
            original_content = path.read_text(encoding="utf-8")

            with (
                patch("backend.settings.store.os.replace", side_effect=OSError("disk unavailable")),
                self.assertRaisesRegex(SettingsFileError, "disk unavailable"),
            ):
                store.save(settings)

            self.assertEqual(path.read_text(encoding="utf-8"), original_content)
            self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_invalid_ini_is_reported_without_falling_back(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "settings.ini"
            path.write_text("[settings\nschema_version = 1", encoding="utf-8")

            with self.assertRaisesRegex(SettingsFileError, "invalid INI"):
                SettingsStore(path).load()

    def test_neighboring_settings_json_is_ignored(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            path = root / "settings.ini"
            defaults = AppSettings.defaults(root / "home")
            json_path = root / "settings.json"
            json_path.write_text('{"ignored": true}', encoding="utf-8")

            loaded = SettingsStore(path, defaults).load()

            self.assertEqual(loaded, defaults)
            self.assertTrue(path.exists())
            self.assertIn("[whisper]", path.read_text(encoding="utf-8"))
            self.assertEqual(json_path.read_text(encoding="utf-8"), '{"ignored": true}')


class DirectoryValidationTests(unittest.TestCase):
    def test_inspection_reports_missing_directories_without_creating(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings = AppSettings.defaults(Path(temporary_directory))

            statuses = inspect_directories(settings.directories)

            self.assertTrue(all(not status.ready for status in statuses))
            self.assertTrue(all(status.error == "directory does not exist" for status in statuses))
            self.assertFalse(settings.directories.input.exists())

    def test_ensure_directories_creates_all_configured_paths(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings = AppSettings.defaults(Path(temporary_directory))

            statuses = ensure_directories(settings.directories)

            self.assertTrue(all(status.ready for status in statuses))
            self.assertTrue(settings.directories.input.is_dir())
            self.assertTrue(settings.directories.output.is_dir())
            self.assertTrue(settings.directories.archive.is_dir())
            self.assertTrue(settings.directories.transcripts.is_dir())

    def test_existing_file_is_rejected_as_a_directory(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            settings = AppSettings.defaults(root)
            settings.directories.input.parent.mkdir(parents=True)
            settings.directories.input.write_text("not a directory")

            with self.assertRaises(DirectoryAccessError) as caught:
                ensure_directories(settings.directories)

            self.assertEqual(caught.exception.statuses[0].field, "directories.input")
            self.assertEqual(caught.exception.statuses[0].error, "path is not a directory")


class SettingsResolutionTests(unittest.TestCase):
    def test_persisted_directories_are_resolved(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            defaults = AppSettings.defaults(root / "home")
            store = SettingsStore(root / "settings.ini", defaults)
            store.save(defaults)

            paths = resolve_runtime_paths(store)

            self.assertEqual(paths.ready, defaults.directories.input)
            self.assertEqual(paths.finished, defaults.directories.output)

    def test_legacy_environment_root_overrides_only_directories(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            defaults = replace(
                AppSettings.defaults(root / "home"),
                processing=replace(AppSettings.defaults().processing, mode="report_only"),
            )
            store = SettingsStore(root / "settings.ini", defaults)
            legacy_root = root / "legacy"

            with patch.dict(
                os.environ,
                {"CENSOR_PROJECT_ROOT": str(legacy_root)},
            ):
                effective = load_effective_settings(store)

            self.assertEqual(effective.directories.input, (legacy_root / "ready").resolve())
            self.assertEqual(effective.directories.output, (legacy_root / "finished").resolve())
            self.assertEqual(effective.processing.mode, "report_only")


if __name__ == "__main__":
    unittest.main()
