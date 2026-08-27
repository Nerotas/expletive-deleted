import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.jobs.batch import output_path, process_file
from backend.runtime import RuntimePaths, get_runtime_paths


class BatchLifecycleTests(unittest.TestCase):
    def create_source(self, root: str) -> tuple[RuntimePaths, Path]:
        paths = get_runtime_paths(Path(root))
        paths.create()
        source = paths.ready / "movie.mkv"
        source.write_bytes(b"source")
        return paths, source

    def test_success_creates_finished_output_before_archiving_source(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            paths, source = self.create_source(temporary_directory)
            destination = output_path(source, paths.finished)
            censor = MagicMock()

            def create_output(**options) -> bool:
                self.assertFalse(options["report_only"])
                destination.write_bytes(b"output")
                return True

            censor.process.side_effect = create_output
            censor.review_candidates = []
            censor.used_cached_transcript = False
            censor.profane_count = 1

            with patch("backend.jobs.batch.ProfanityCensor", return_value=censor):
                result = process_file(
                    source,
                    "large",
                    paths,
                    1,
                    1,
                    archive_after_success=True,
                )

            self.assertEqual(result[0], "ok")
            self.assertTrue(destination.is_file())
            self.assertFalse(source.exists())
            self.assertTrue((paths.processed / source.name).is_file())

    def test_success_retains_source_when_archiving_is_disabled(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            paths, source = self.create_source(temporary_directory)
            destination = output_path(source, paths.finished)
            censor = MagicMock()

            def create_output(**options) -> bool:
                self.assertFalse(options["report_only"])
                return destination.write_bytes(b"output") > 0

            censor.process.side_effect = create_output
            censor.review_candidates = []
            censor.used_cached_transcript = False
            censor.profane_count = 1

            with patch("backend.jobs.batch.ProfanityCensor", return_value=censor):
                result = process_file(source, "large", paths, 1, 1)

            self.assertEqual(result[0], "ok")
            self.assertTrue(source.is_file())
            self.assertFalse((paths.processed / source.name).exists())

    def test_archive_collision_fails_and_retains_source(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            paths, source = self.create_source(temporary_directory)
            destination = output_path(source, paths.finished)
            destination.write_bytes(b"output")
            archive_path = paths.processed / source.name
            archive_path.write_bytes(b"existing archive")
            censor = MagicMock()
            censor.process.return_value = True
            censor.review_candidates = []
            censor.used_cached_transcript = False
            censor.profane_count = 1

            with patch("backend.jobs.batch.ProfanityCensor", return_value=censor):
                result = process_file(
                    source,
                    "large",
                    paths,
                    1,
                    1,
                    overwrite=True,
                    archive_after_success=True,
                )

            self.assertEqual(result[0], "fail")
            self.assertTrue(source.is_file())
            self.assertEqual(archive_path.read_bytes(), b"existing archive")

    def test_failure_leaves_source_in_ready(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            paths, source = self.create_source(temporary_directory)
            censor = MagicMock()
            censor.process.return_value = False
            censor.review_candidates = []
            censor.used_cached_transcript = False
            censor.profane_count = 0

            with patch("backend.jobs.batch.ProfanityCensor", return_value=censor):
                result = process_file(
                    source,
                    "large",
                    paths,
                    1,
                    1,
                )

            self.assertEqual(result[0], "fail")
            self.assertTrue(source.is_file())
            self.assertFalse((paths.processed / source.name).exists())

    def test_report_only_leaves_source_in_ready(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            paths, source = self.create_source(temporary_directory)
            censor = MagicMock()
            censor.process.return_value = True
            censor.review_candidates = []
            censor.used_cached_transcript = False
            censor.profane_count = 1

            with patch("backend.jobs.batch.ProfanityCensor", return_value=censor):
                result = process_file(
                    source,
                    "large",
                    paths,
                    1,
                    1,
                    report_only=True,
                )

            self.assertEqual(result[0], "ok")
            self.assertTrue(source.is_file())
            self.assertFalse((paths.processed / source.name).exists())


if __name__ == "__main__":
    unittest.main()