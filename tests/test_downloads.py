import tempfile
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import MagicMock, patch

from backend.jobs.downloads import (
    BrowserCookiesUnavailable,
    DownloadManager,
    DownloadRecord,
    YtdlpAuthenticationRequired,
    YtdlpJavaScriptChallengeUnsolved,
    validate_youtube_url,
)
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

    def test_dpapi_cookie_failure_offers_another_browser_session(self):
        error = DownloadManager._download_error("ERROR: Failed to decrypt with DPAPI")

        self.assertIsInstance(error, BrowserCookiesUnavailable)
        self.assertEqual(error.code, "browser_cookies_unavailable")

    def test_chromium_cookie_copy_failure_offers_another_browser_session(self):
        error = DownloadManager._download_error("ERROR: Could not copy Chrome cookie database")

        self.assertIsInstance(error, BrowserCookiesUnavailable)
        self.assertEqual(error.code, "browser_cookies_unavailable")

    def test_unsolved_js_challenge_recommends_installing_a_runtime(self):
        output = (
            "WARNING: [youtube] ohNTpnAs62E: n challenge solving failed: Some formats may be missing\n"
            "WARNING: Only images are available for download. use --list-formats to see them\n"
            "ERROR: [youtube] ohNTpnAs62E: Requested format is not available. Use --list-formats for a list of available formats"
        )
        error = DownloadManager._download_error(output)

        self.assertIsInstance(error, YtdlpJavaScriptChallengeUnsolved)
        self.assertEqual(error.code, "javascript_runtime_required")
        self.assertIn("Deno", error.diagnostic)
        self.assertIn(output, error.diagnostic)

    def test_generic_download_failure_preserves_full_diagnostic_output(self):
        output = (
            "WARNING: [youtube] Some web client https formats have been skipped as they are missing a url\n"
            "ERROR: [youtube] ohNTpnAs62E: Requested format is not available. Use --list-formats for a list of available formats"
        )
        error = DownloadManager._download_error(output)

        self.assertEqual(str(error), "ERROR: [youtube] ohNTpnAs62E: Requested format is not available. Use --list-formats for a list of available formats")
        self.assertEqual(error.diagnostic, output)

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

    def test_cookie_failure_during_download_is_classified_not_generic(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            ytdlp = root / "yt-dlp.exe"
            ytdlp.touch()
            settings = AppSettings(
                directories=DirectorySettings(root / "Ready", root / "Finished", root / "Processed", root / "Transcripts"),
                runtime=RuntimeSettings(ytdlp_path=ytdlp),
            )
            manager = DownloadManager(settings)
            job_id = "download-job"
            manager._records[job_id] = DownloadRecord(job_id, "https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ", cookie_browser="brave")
            manager._events[job_id] = []
            manager._cancellations[job_id] = Event()
            process = MagicMock(returncode=1)
            process.stdout = iter(["ERROR: Could not copy Chrome cookie database\n"])

            with (
                patch.object(manager, "_runtime_media_tools", return_value=(Path("ffmpeg"), Path("ffprobe"))),
                patch("backend.jobs.downloads.subprocess.Popen", return_value=process),
            ):
                manager._run(job_id)

        failed = manager.list()[0]
        self.assertEqual(failed.status, "failed")
        self.assertEqual(failed.error.code, "browser_cookies_unavailable")

    def test_download_format_selection_is_not_restricted_to_avc1_or_mp4a(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            ytdlp = root / "yt-dlp.exe"
            ytdlp.touch()
            settings = AppSettings(
                directories=DirectorySettings(root / "Ready", root / "Finished", root / "Processed", root / "Transcripts"),
                runtime=RuntimeSettings(ytdlp_path=ytdlp),
            )
            manager = DownloadManager(settings)
            job_id = "download-job"
            manager._records[job_id] = DownloadRecord(job_id, "https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ")
            manager._events[job_id] = []
            manager._cancellations[job_id] = Event()
            process = MagicMock(returncode=1)
            process.stdout = iter([])

            with (
                patch.object(manager, "_runtime_media_tools", return_value=(Path("ffmpeg"), Path("ffprobe"))),
                patch("backend.jobs.downloads.subprocess.Popen", return_value=process) as popen,
            ):
                manager._run(job_id)

        command = popen.call_args.args[0]
        format_selector = command[command.index("-f") + 1]
        self.assertNotIn("avc1", format_selector)
        self.assertNotIn("mp4a", format_selector)

    def test_download_falls_back_to_tv_client_when_web_only_serves_sabr(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            ytdlp = root / "yt-dlp.exe"
            ytdlp.touch()
            settings = AppSettings(
                directories=DirectorySettings(root / "Ready", root / "Finished", root / "Processed", root / "Transcripts"),
                runtime=RuntimeSettings(ytdlp_path=ytdlp),
            )
            manager = DownloadManager(settings)
            job_id = "download-job"
            manager._records[job_id] = DownloadRecord(job_id, "https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ")
            manager._events[job_id] = []
            manager._cancellations[job_id] = Event()
            process = MagicMock(returncode=1)
            process.stdout = iter([])

            with (
                patch.object(manager, "_runtime_media_tools", return_value=(Path("ffmpeg"), Path("ffprobe"))),
                patch("backend.jobs.downloads.subprocess.Popen", return_value=process) as popen,
            ):
                manager._run(job_id)

        command = popen.call_args.args[0]
        self.assertEqual(command[command.index("--extractor-args") + 1], "youtube:player_client=default,tv")

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