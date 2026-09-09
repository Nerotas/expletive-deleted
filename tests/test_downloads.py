import tempfile
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import MagicMock, patch

from backend.jobs.downloads import DownloadManager, DownloadRecord, YtdlpAuthenticationRequired, validate_youtube_url
from backend.settings import AppSettings, DirectorySettings, RuntimeSettings


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
        self.assertIn("--ignore-config", run.call_args.args[0])
        self.assertIn("--dump-single-json", run.call_args.args[0])
        self.assertIn("--skip-download", run.call_args.args[0])

    def test_metadata_uses_selected_browser_cookies_only_when_requested(self):
        completed = MagicMock(returncode=0, stdout='{"title": "Example Movie"}', stderr="")
        with patch("backend.jobs.downloads.subprocess.run", return_value=completed) as run:
            DownloadManager._resolve_title(Path("C:/Tools/yt-dlp.exe"), "https://youtu.be/dQw4w9WgXcQ", "edge")

        self.assertIn("--cookies-from-browser", run.call_args.args[0])
        self.assertIn("edge", run.call_args.args[0])

    def test_authentication_output_is_classified_without_opening_a_browser(self):
        error = DownloadManager._download_error("ERROR: Sign in to confirm you're not a bot")

        self.assertIsInstance(error, YtdlpAuthenticationRequired)
        self.assertEqual(error.code, "authentication_required")

    def test_remote_job_keeps_url_out_of_filesystem_source_model(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            ytdlp = root / "yt-dlp.exe"
            ytdlp.touch()
            settings = AppSettings(
                directories=DirectorySettings(root / "Ready", root / "Finished", root / "Processed", root / "Transcripts"),
                runtime=RuntimeSettings(ytdlp_path=ytdlp),
            )
            manager = DownloadManager(settings)
            manager._executor.submit = MagicMock()
            with patch.object(manager, "_resolve_title", return_value="Example Movie"):
                job = manager.submit("https://youtu.be/dQw4w9WgXcQ")

        self.assertEqual(job.to_dict()["source_type"], "youtube")
        self.assertEqual(job.to_dict()["source"], "https://youtu.be/dQw4w9WgXcQ")
        self.assertEqual(job.title, "Example Movie")
        self.assertEqual(manager.events(job.id)[0].to_dict()["stage"], "queued")

    def test_retry_reuses_the_original_queue_record(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            ytdlp = root / "yt-dlp.exe"
            ytdlp.touch()
            settings = AppSettings(
                directories=DirectorySettings(root / "Ready", root / "Finished", root / "Processed", root / "Transcripts"),
                runtime=RuntimeSettings(ytdlp_path=ytdlp),
            )
            manager = DownloadManager(settings)
            manager._executor.submit = MagicMock()
            with patch.object(manager, "_resolve_title", return_value="Example Movie"):
                first = manager.submit("https://youtu.be/dQw4w9WgXcQ")
                retry = manager.submit(first.url, first.id)

        self.assertEqual(retry.id, first.id)
        self.assertEqual(len(manager.list()), 1)

    def test_preserve_source_youtube_import_never_encodes_after_remux_failure(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            settings = AppSettings(directories=DirectorySettings(root / "Ready", root / "Finished", root / "Processed", root / "Transcripts"))
            manager = DownloadManager(settings)
            source, final = root / "source.webm", root / "final.mp4"
            source.touch()
            failed_copy = MagicMock(returncode=1, stdout="copy failed", stderr="copy failed")

            with (
                patch.object(manager, "_duration", return_value=None),
                patch.object(manager, "_run_ffmpeg", return_value=failed_copy) as run,
                patch("backend.jobs.downloads.select_working_video_encoder") as select_encoder,
                self.assertRaisesRegex(RuntimeError, "Choose Convert to H.264"),
            ):
                manager._prepare("download-job", source, final, "ffmpeg", "ffprobe", Event())

        self.assertEqual(run.call_count, 1)
        select_encoder.assert_not_called()

    def test_ffmpeg_preparation_emits_media_time_progress(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            settings = AppSettings(directories=DirectorySettings(root / "Ready", root / "Finished", root / "Processed", root / "Transcripts"))
            manager = DownloadManager(settings)
            job_id = "download-job"
            manager._records[job_id] = DownloadRecord(job_id, "https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ", status="preparing")
            manager._events[job_id] = []
            process = MagicMock(returncode=0)
            process.stdout = iter(["out_time_us=5000000\n", "progress=continue\n"])

            with patch("backend.jobs.downloads.subprocess.Popen", return_value=process) as popen:
                manager._run_ffmpeg(job_id, ["ffmpeg", "-i", "source.mkv", "output.mp4"], Event(), 10.0)

        self.assertIn("-progress", popen.call_args.args[0])
        self.assertEqual(manager.list()[0].progress_percent, 50.0)
        self.assertTrue(any(event.event == "progress" and event.percent == 50.0 for event in manager.events(job_id)))