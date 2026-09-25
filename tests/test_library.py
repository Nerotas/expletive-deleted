import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tests.media_fixtures import provenance

from backend.service import LibraryScanError, scan_library
from backend.settings import AppSettings, DirectorySettings


class LibraryScannerTests(unittest.TestCase):
    def create_settings(self, root: Path) -> AppSettings:
        directories = DirectorySettings(
            input=root / "Ready",
            output=root / "Finished",
            archive=root / "Processed",
            transcripts=root / "Transcripts",
        )
        for path in (
            directories.input,
            directories.output,
            directories.archive,
            directories.transcripts,
        ):
            path.mkdir()
        return AppSettings(directories=directories)

    def test_scan_maps_artifacts_to_persistent_statuses(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings = self.create_settings(Path(temporary_directory))
            ready = settings.directories.input
            ready_source = ready / "Alpha.mp4"
            transcribed_source = ready / "beta.mkv"
            finished_source = ready / "Gamma.wav"
            for source in (ready_source, transcribed_source, finished_source):
                source.write_bytes(b"source")
            (ready / "notes.txt").write_text("ignored", encoding="utf-8")

            transcript = settings.directories.transcripts / "beta.mkv-transcript.json"
            transcript.write_text("{}", encoding="utf-8")
            finished_transcript = settings.directories.transcripts / "Gamma.wav-transcript.json"
            finished_transcript.write_text("{}", encoding="utf-8")
            output = settings.directories.output / "Gamma.wav-censored.mp3"
            output.write_bytes(b"output")
            provenance(finished_source, output)

            with patch(
                "backend.service.library.transcript_cache_is_compatible",
                side_effect=lambda _source, candidate, _ffprobe, *_profile: Path(candidate) == transcript,
            ), patch("backend.service.library._probe_duration", return_value=125.25):
                items = scan_library(settings, ffprobe_bin="ffprobe")

        self.assertEqual([item.source.name for item in items], ["Alpha.mp4", "beta.mkv", "Gamma.wav"])
        self.assertEqual([item.status for item in items], ["ready", "transcribed", "finished"])
        self.assertEqual(items[1].transcript, transcript)
        self.assertEqual(items[2].output, output)
        self.assertEqual(items[2].to_dict()["status"], "finished")
        self.assertIsInstance(items[0].date_added, datetime)
        self.assertEqual(items[0].date_added.tzinfo, timezone.utc)
        self.assertEqual(items[0].to_dict()["date_added"], items[0].date_added.isoformat())
        self.assertEqual(items[0].to_dict()["duration_seconds"], 125.25)

    def test_scan_caches_duration_until_the_source_changes(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings = self.create_settings(Path(temporary_directory))
            source = settings.directories.input / "movie.mp4"
            source.write_bytes(b"source")
            cache = {}
            completed = SimpleNamespace(returncode=0, stdout="3723.4\n")

            with patch("backend.service.library.subprocess.run", return_value=completed) as run:
                first = scan_library(settings, ffprobe_bin="ffprobe", duration_cache=cache)
                second = scan_library(settings, ffprobe_bin="ffprobe", duration_cache=cache)
                source.write_bytes(b"changed source")
                third = scan_library(settings, ffprobe_bin="ffprobe", duration_cache=cache)

        self.assertEqual(first[0].duration_seconds, 3723.4)
        self.assertEqual(second[0].duration_seconds, 3723.4)
        self.assertEqual(third[0].duration_seconds, 3723.4)
        self.assertEqual(run.call_count, 2)
        self.assertIn("file,pipe", run.call_args.args[0])

    def test_missing_input_directory_is_reported(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            settings = AppSettings(
                directories=DirectorySettings(
                    input=root / "missing",
                    output=root / "Finished",
                    archive=root / "Processed",
                    transcripts=root / "Transcripts",
                )
            )

            with self.assertRaisesRegex(LibraryScanError, "not available"):
                scan_library(settings, ffprobe_bin="ffprobe")


if __name__ == "__main__":
    unittest.main()
