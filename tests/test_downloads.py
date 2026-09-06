import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.jobs.downloads import DownloadManager, validate_youtube_url
from backend.settings import AppSettings, DirectorySettings


class YoutubeUrlTests(unittest.TestCase):
    def test_individual_youtube_urls_are_accepted(self):
        url, video_id = validate_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(url, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(video_id, "dQw4w9WgXcQ")

    def test_other_sites_and_playlist_only_urls_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Only individual"):
            validate_youtube_url("https://example.com/video")
        with self.assertRaisesRegex(ValueError, "Playlists"):
            validate_youtube_url("https://www.youtube.com/watch?list=PL123")


class DownloadManagerTests(unittest.TestCase):
    def test_metadata_title_uses_ytdlp_json_output(self):
        completed = MagicMock(returncode=0, stdout='{"title": "Example Movie"}', stderr="")
        with patch("backend.jobs.downloads.subprocess.run", return_value=completed) as run:
            title = DownloadManager._resolve_title(Path("C:/Tools/yt-dlp.exe"), "https://youtu.be/dQw4w9WgXcQ")

        self.assertEqual(title, "Example Movie")
        self.assertIn("--dump-single-json", run.call_args.args[0])
        self.assertIn("--skip-download", run.call_args.args[0])

    def test_remote_job_keeps_url_out_of_filesystem_source_model(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            settings = AppSettings(directories=DirectorySettings(root / "Ready", root / "Finished", root / "Processed", root / "Transcripts"))
            manager = DownloadManager(settings)
            manager._executor.submit = MagicMock()
            job = manager.submit("https://youtu.be/dQw4w9WgXcQ")

        self.assertEqual(job.to_dict()["source_type"], "youtube")
        self.assertEqual(job.to_dict()["source"], "https://youtu.be/dQw4w9WgXcQ")
        self.assertEqual(manager.events(job.id)[0].to_dict()["stage"], "queued")

    def test_retry_reuses_the_original_queue_record(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            settings = AppSettings(directories=DirectorySettings(root / "Ready", root / "Finished", root / "Processed", root / "Transcripts"))
            manager = DownloadManager(settings)
            manager._executor.submit = MagicMock()
            first = manager.submit("https://youtu.be/dQw4w9WgXcQ")
            retry = manager.submit(first.url, first.id)

        self.assertEqual(retry.id, first.id)
        self.assertEqual(len(manager.list()), 1)