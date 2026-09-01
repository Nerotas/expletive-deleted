import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.policy import PolicyFileError, PolicyStore


class DurablePolicyStoreTests(unittest.TestCase):
    def create_store(self, root: Path) -> PolicyStore:
        defaults = root / "defaults"
        defaults.mkdir(exist_ok=True)
        censor_path = defaults / "profanity_censor_words.txt"
        exclusions_path = defaults / "profanity_exclusions.txt"
        censor_path.write_text("default-censor\nshared\n", encoding="utf-8")
        exclusions_path.write_text("default-exclusion\nshared\n", encoding="utf-8")
        return PolicyStore(
            root / "dictionary" / "profanity.json",
            censor_defaults_path=censor_path,
            exclusions_defaults_path=exclusions_path,
            legacy_path=root / "policy.json",
        )

    def test_first_load_seeds_complete_dictionary_from_defaults(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = self.create_store(Path(temporary_directory))

            policy = store.load()
            payload = json.loads(store.path.read_text(encoding="utf-8"))

            self.assertEqual(policy.censor_words, {"default-censor"})
            self.assertEqual(policy.exclusions, {"default-exclusion", "shared"})
            self.assertEqual(
                payload,
                {
                    "schema_version": 1,
                    "seeded_from_default_version": 1,
                    "words": ["default-censor"],
                    "exclusions": ["default-exclusion", "shared"],
                },
            )

    def test_existing_dictionary_does_not_reread_changed_or_missing_defaults(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = self.create_store(Path(temporary_directory))
            expected = store.load()
            store.censor_defaults_path.unlink()
            store.exclusions_defaults_path.unlink()

            loaded = store.load()

            self.assertEqual(loaded.censor_words, expected.censor_words)
            self.assertEqual(loaded.exclusions, expected.exclusions)

    def test_all_update_operations_persist_across_store_instances(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = self.create_store(root)
            store.update("censor", "custom-censor", "add")
            store.update("exclude", "custom-exclusion", "add")
            store.update("censor", "default-censor", "remove")
            store.update("exclude", "default-exclusion", "remove")

            loaded = self.create_store(root).load()

            self.assertEqual(loaded.censor_words, {"custom-censor"})
            self.assertEqual(loaded.exclusions, {"custom-exclusion", "shared"})

    def test_legacy_overrides_are_materialized_without_modifying_source(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = self.create_store(root)
            legacy_payload = {
                "schema_version": 1,
                "overrides": {
                    "custom-censor": "censor",
                    "custom-exclusion": "exclude",
                    "default-censor": "none",
                    "default-exclusion": "censor",
                },
            }
            store.legacy_path.write_text(json.dumps(legacy_payload), encoding="utf-8")
            source_before = store.legacy_path.read_bytes()

            policy = store.load()

            self.assertEqual(policy.censor_words, {"custom-censor", "default-exclusion"})
            self.assertEqual(policy.exclusions, {"custom-exclusion", "shared"})
            self.assertEqual(store.legacy_path.read_bytes(), source_before)

    def test_failed_legacy_migration_leaves_source_and_destination_untouched(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = self.create_store(root)
            store.legacy_path.write_text('{"schema_version":1,"overrides":[]}', encoding="utf-8")
            source_before = store.legacy_path.read_bytes()

            with self.assertRaisesRegex(PolicyFileError, "overrides must be an object"):
                store.load()

            self.assertFalse(store.path.exists())
            self.assertEqual(store.legacy_path.read_bytes(), source_before)

    def test_restore_defaults_uses_current_factory_dictionary(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = self.create_store(Path(temporary_directory))
            store.update("censor", "custom", "add")
            store.censor_defaults_path.write_text("new-default\n", encoding="utf-8")
            store.exclusions_defaults_path.write_text("new-exclusion\n", encoding="utf-8")

            restored = store.restore_defaults()

            self.assertEqual(restored.censor_words, {"new-default"})
            self.assertEqual(restored.exclusions, {"new-exclusion"})

    def test_import_validates_before_replacing_and_export_is_complete(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = self.create_store(root)
            store.load()
            invalid = root / "invalid.json"
            invalid.write_text('{"words":[]}', encoding="utf-8")
            before = store.path.read_bytes()

            with self.assertRaises(PolicyFileError):
                store.import_dictionary(invalid)
            self.assertEqual(store.path.read_bytes(), before)

            imported = root / "import.json"
            imported.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "seeded_from_default_version": 1,
                        "words": ["portable-censor"],
                        "exclusions": ["portable-exclusion"],
                    }
                ),
                encoding="utf-8",
            )
            store.import_dictionary(imported)
            exported = root / "export" / "dictionary.json"
            store.export_dictionary(exported)

            self.assertEqual(
                json.loads(exported.read_text(encoding="utf-8")),
                {
                    "schema_version": 1,
                    "seeded_from_default_version": 1,
                    "words": ["portable-censor"],
                    "exclusions": ["portable-exclusion"],
                },
            )

    def test_failed_replace_preserves_existing_dictionary_and_removes_temporary_file(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = self.create_store(Path(temporary_directory))
            store.load()
            prior = store.path.read_bytes()

            with (
                patch("backend.policy.store.os.replace", side_effect=OSError("disk unavailable")),
                self.assertRaisesRegex(PolicyFileError, "disk unavailable"),
            ):
                store.update("censor", "custom", "add")

            self.assertEqual(store.path.read_bytes(), prior)
            self.assertEqual(list(store.path.parent.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()