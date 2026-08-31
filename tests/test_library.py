import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

            transcript = settings.directories.transcripts / "beta-transcript.json"
            transcript.write_text("{}", encoding="utf-8")
            finished_transcript = settings.directories.transcripts / "Gamma-transcript.json"
            finished_transcript.write_text("{}", encoding="utf-8")
            output = settings.directories.output / "Gamma-censored.mp3"
            output.write_bytes(b"output")

            with patch(
                "backend.service.library.transcript_cache_is_compatible",
                side_effect=lambda _source, candidate, _ffprobe, *_profile: Path(candidate) == transcript,
            ):
                items = scan_library(settings, ffprobe_bin="ffprobe")

        self.assertEqual([item.source.name for item in items], ["Alpha.mp4", "beta.mkv", "Gamma.wav"])
        self.assertEqual([item.status for item in items], ["ready", "transcribed", "finished"])
        self.assertEqual(items[1].transcript, transcript)
        self.assertEqual(items[2].output, output)
        self.assertEqual(items[2].to_dict()["status"], "finished")

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
