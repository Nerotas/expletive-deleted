import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.censor import ProfanityCensor
from backend.policy import PolicyFileError, PolicyStore, ProfanityPolicy


class PolicyStoreTests(unittest.TestCase):
    def create_store(
        self,
        root: Path,
        censor_words: str = "default-censor\n",
        exclusions: str = "default-exclusion\n",
    ) -> PolicyStore:
        censor_path = root / "profanity_censor_words.txt"
        exclusions_path = root / "profanity_exclusions.txt"
        censor_path.write_text(censor_words, encoding="utf-8")
        exclusions_path.write_text(exclusions, encoding="utf-8")
        return PolicyStore(
            root / "dictionary" / "profanity.json",
            censor_defaults_path=censor_path,
            exclusions_defaults_path=exclusions_path,
            legacy_path=root / "policy.json",
        )

    def test_missing_user_policy_seeds_complete_dictionary(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = self.create_store(root)

            policy = store.load()

            self.assertEqual(policy.censor_words, {"default-censor"})
            self.assertEqual(policy.exclusions, {"default-exclusion"})
            self.assertTrue(store.path.exists())

    def test_user_changes_are_atomic_snapshots_and_do_not_mutate_defaults(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = self.create_store(root)
            censor_before = store.censor_defaults_path.read_text(encoding="utf-8")
            exclusions_before = store.exclusions_defaults_path.read_text(encoding="utf-8")

            policy, changed = store.update("censor", "custom word", "add")

            payload = json.loads(store.path.read_text(encoding="utf-8"))
            self.assertTrue(changed)
            self.assertIn("custom word", policy.censor_words)
            self.assertEqual(
                [(entry["value"], entry["source"]) for entry in payload["words"]],
                [("custom word", "user"), ("default-censor", "default")],
            )
            self.assertEqual(
                [(entry["value"], entry["source"]) for entry in payload["exclusions"]],
                [("default-exclusion", "default")],
            )
            self.assertEqual(
                store.censor_defaults_path.read_text(encoding="utf-8"),
                censor_before,
            )
            self.assertEqual(
                store.exclusions_defaults_path.read_text(encoding="utf-8"),
                exclusions_before,
            )

    def test_removed_word_and_existing_dictionary_ignore_new_defaults(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = self.create_store(root)

            store.update("censor", "default-censor", "remove")
            store.censor_defaults_path.write_text(
                "default-censor\nnew-default\n",
                encoding="utf-8",
            )
            policy = store.load()

            self.assertNotIn("default-censor", policy.censor_words)
            self.assertNotIn("new-default", policy.censor_words)
            self.assertEqual(json.loads(store.path.read_text(encoding="utf-8"))["words"], [])

    def test_classification_is_mutually_exclusive(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = self.create_store(Path(temporary_directory))

            moved, _ = store.update("exclude", "default-censor", "add")
            restored, _ = store.update("censor", "default-censor", "add")

            self.assertIn("default-censor", moved.exclusions)
            self.assertNotIn("default-censor", moved.censor_words)
            self.assertIn("default-censor", restored.censor_words)
            self.assertNotIn("default-censor", restored.exclusions)
            self.assertEqual(restored.overrides_count, 0)

    def test_failed_replace_preserves_existing_policy(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = self.create_store(Path(temporary_directory))
            store.update("censor", "first", "add")
            prior = store.path.read_text(encoding="utf-8")

            with (
                patch("backend.policy.store.os.replace", side_effect=OSError("disk unavailable")),
                self.assertRaisesRegex(PolicyFileError, "disk unavailable"),
            ):
                store.update("censor", "second", "add")

            self.assertEqual(store.path.read_text(encoding="utf-8"), prior)
            self.assertEqual(list(store.path.parent.glob("*.tmp")), [])

    def test_malformed_policy_is_actionable_and_never_silently_ignored(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = self.create_store(Path(temporary_directory))
            store.path.parent.mkdir(parents=True)
            store.path.write_text(
                '{"schema_version":1,"seeded_from_default_version":1,"words":{},"exclusions":[]}',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(PolicyFileError, "words must be an array"):
                store.load()

    def test_processing_engine_loads_the_same_effective_policy(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            policy_store = MagicMock()
            policy_store.load.return_value = ProfanityPolicy(
                censor_words=frozenset({"custom-censor"}),
                exclusions=frozenset({"custom-exclusion"}),
                censor_defaults_path=root / "censor.txt",
                exclusions_defaults_path=root / "exclude.txt",
                overrides_path=root / "policy.json",
                overrides_count=2,
            )
            with (
                patch("backend.censor.engine.find_ffmpeg", return_value="ffmpeg"),
                patch("backend.censor.engine.find_ffprobe", return_value="ffprobe"),
                patch("backend.censor.engine.available_encoders", return_value={"libx264"}),
                patch(
                    "backend.censor.engine.select_working_video_encoder",
                    return_value="libx264",
                ),
            ):
                censor = ProfanityCensor(
                    "input.mkv",
                    "output.mkv",
                    whisper_cache_dir=root,
                    policy_store=policy_store,
                )

            self.assertEqual(censor.censor_words, {"custom-censor"})
            self.assertEqual(censor.exclude_words, {"custom-exclusion"})
            self.assertEqual(censor.policy_file, root / "policy.json")


if __name__ == "__main__":
    unittest.main()
