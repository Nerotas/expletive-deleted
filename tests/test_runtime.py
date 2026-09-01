import importlib
import json
import os
import io
import tempfile
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import MagicMock, patch

from backend.censor.engine import (
    ProcessingCancelled,
    ProfanityCensor,
    TranscriptValidationError,
    run_ffmpeg_with_progress,
    transcript_cache_is_compatible,
    validate_transcript_data,
    write_transcript_atomic,
)
from better_profanity import profanity
from backend.runtime.environment import (
    PROJECT_ROOT,
    available_encoders,
    add_word_to_list,
    ensure_executable_directory_on_path,
    find_ffmpeg,
    find_ffprobe,
    get_profanity_censor_words_file,
    get_profanity_exclusions_file,
    get_calibrated_transcription_factor,
    get_whisper_cache_dir,
    get_whisper_device_status,
    record_transcription_timing,
    get_runtime_paths,
    load_profanity_censor_words,
    load_profanity_exclusions,
    remove_word_from_list,
    select_video_encoder,
    select_working_video_encoder,
    require_whisper_model,
)


class RuntimeTests(unittest.TestCase):
    def test_user_policy_edits_preserve_comments_and_validate_entries(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            policy = Path(temporary_directory) / "policy.txt"
            policy.write_text("# Existing policy\nFirst word\n# Keep this\n", encoding="utf-8")

            words, added = add_word_to_list(policy, "  New   Word  ", "Test policy")
            after_removal, removed = remove_word_from_list(policy, "first word", "Test policy")

            self.assertTrue(added)
            self.assertTrue(removed)
            self.assertEqual(words, {"first word", "new word"})
            self.assertEqual(after_removal, {"new word"})
            self.assertIn("# Existing policy", policy.read_text(encoding="utf-8"))
            with self.assertRaisesRegex(ValueError, "comments"):
                add_word_to_list(policy, "not # a word", "Test policy")

    def test_ffmpeg_progress_process_terminates_on_cancellation(self):
        process = MagicMock()
        process.stdout = iter(["progress=continue\n"])
        process.wait.return_value = 1
        cancellation = Event()
        cancellation.set()

        with (
            patch("backend.censor.engine.subprocess.Popen", return_value=process),
            self.assertRaisesRegex(ProcessingCancelled, "cancelled"),
        ):
            run_ffmpeg_with_progress(
                ["ffmpeg", "-i", "input.mkv", "output.mkv"],
                10.0,
                cancellation=cancellation,
            )

        process.terminate.assert_called_once()

    def test_encoder_inventory_excludes_ffmpeg_legend(self):
        completed = MagicMock(
            returncode=0,
            stdout=" V..... = Video\n V....D libx264 H.264\n A....D aac AAC\n",
            stderr="",
        )
        with patch("backend.runtime.environment.subprocess.run", return_value=completed):
            encoders = available_encoders("ffmpeg")

        self.assertEqual(encoders, {"libx264"})

    def test_legacy_censor_module_aliases_packaged_engine(self):
        self.assertIs(
            importlib.import_module("censor_profanity"),
            importlib.import_module("backend.censor.engine"),
        )

    def test_legacy_runtime_module_aliases_packaged_environment(self):
        self.assertIs(
            importlib.import_module("workflow_runtime"),
            importlib.import_module("backend.runtime.environment"),
        )

    def test_default_policy_files_are_packaged_resources(self):
        self.assertEqual(
            get_profanity_censor_words_file(),
            PROJECT_ROOT / "resources" / "profanity_censor_words.txt",
        )
        self.assertEqual(
            get_profanity_exclusions_file(),
            PROJECT_ROOT / "resources" / "profanity_exclusions.txt",
        )
        self.assertTrue(get_profanity_censor_words_file().is_file())
        self.assertTrue(get_profanity_exclusions_file().is_file())

    def test_custom_media_root_does_not_relocate_packaged_policy_defaults(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            runtime_root = Path(temporary_directory)
            self.assertEqual(
                get_profanity_censor_words_file(runtime_root),
                PROJECT_ROOT / "resources" / "profanity_censor_words.txt",
            )
            self.assertEqual(
                get_profanity_exclusions_file(runtime_root),
                PROJECT_ROOT / "resources" / "profanity_exclusions.txt",
            )

    def test_ffmpeg_progress_reports_percent_speed_and_eta(self):
        process = MagicMock()
        process.stdout = iter([
            "fps=48.0\n",
            "out_time=00:00:05.000000\n",
            "speed=2.0x\n",
            "progress=continue\n",
            "out_time=00:00:10.000000\n",
            "progress=end\n",
        ])
        process.wait.return_value = 0

        output = io.StringIO()
        with (
            patch("backend.censor.engine.subprocess.Popen", return_value=process) as popen,
            patch("backend.censor.engine.sys.stdout", output),
        ):
            result = run_ffmpeg_with_progress(["ffmpeg", "-i", "input.mkv", "output.mkv"], 10.0)

        self.assertEqual(result.returncode, 0)
        self.assertIn(" 50%", output.getvalue())
        self.assertIn("speed 2.0x", output.getvalue())
        self.assertIn("eta 00:02", output.getvalue())
        command = popen.call_args.args[0]
        self.assertIn("-progress", command)
        self.assertEqual(command[command.index("-progress") + 1], "pipe:1")

    def test_clean_file_copy_uses_ffmpeg_progress(self):
        censor = object.__new__(ProfanityCensor)
        censor.input_file = "input.mkv"
        censor.output_file = "output.mkv"
        censor.ffmpeg_bin = "ffmpeg"
        censor.has_discrete_center_audio = MagicMock(return_value=False)
        censor.get_media_duration_seconds = MagicMock(return_value=90.0)
        censor.is_audio_only = MagicMock(return_value=False)
        censor.get_video_codec = MagicMock(return_value="h264")
        completed = MagicMock(returncode=0, stderr="")

        with patch("backend.censor.engine.run_ffmpeg_with_progress", return_value=completed) as run:
            success = censor.censor_video([])

        self.assertTrue(success)
        self.assertEqual(run.call_args.args[1], 90.0)
        self.assertIn("copy", run.call_args.args[0])

    def test_clean_hevc_source_is_encoded_when_h264_is_requested(self):
        censor = object.__new__(ProfanityCensor)
        censor.input_file = "input.mkv"
        censor.output_file = "output.mkv"
        censor.ffmpeg_bin = "ffmpeg"
        censor.censor_method = "mute"
        censor.video_mode = "h264"
        censor.video_encoder = "libx264"
        censor.encoders = {"libx264"}
        censor.has_discrete_center_audio = MagicMock(return_value=False)
        censor.get_media_duration_seconds = MagicMock(return_value=90.0)
        censor.is_audio_only = MagicMock(return_value=False)
        censor.get_video_codec = MagicMock(return_value="hevc")
        completed = MagicMock(returncode=0, stderr="")

        with patch("backend.censor.engine.run_ffmpeg_with_progress", return_value=completed) as run:
            success = censor.censor_video([])

        self.assertTrue(success)
        command = run.call_args.args[0]
        self.assertEqual(command[command.index("-c:v") + 1], "libx264")

    def test_5_1_layout_detection_requires_six_channels(self):
        censor = object.__new__(ProfanityCensor)
        censor.get_audio_stream_info = MagicMock(return_value=(6, "5.1(side)"))
        self.assertTrue(censor.is_5_1_audio())

        censor.get_audio_stream_info.return_value = (6, "unknown")
        self.assertFalse(censor.is_5_1_audio())

    def test_7_1_layout_detection_requires_eight_channels(self):
        censor = object.__new__(ProfanityCensor)
        censor.get_audio_stream_info = MagicMock(return_value=(8, "7.1(wide-side)"))
        self.assertTrue(censor.has_discrete_center_audio())

        censor.get_audio_stream_info.return_value = (10, "7.1.2")
        self.assertFalse(censor.has_discrete_center_audio())

    def test_5_1_filter_drops_only_front_center(self):
        censor = object.__new__(ProfanityCensor)
        censor.get_audio_stream_info = MagicMock(return_value=(6, "5.1"))

        graph = censor.generate_karaoke_filter_complex([{"start": 1.0, "end": 2.0}])

        self.assertIn("pan=5.1|c0=c0|c1=c1|c2=0*c2|c3=c3|c4=c4|c5=c5", graph)
        self.assertIn("between(t,0.85,2.15)", graph)

    def test_configured_padding_is_applied_to_intervals(self):
        censor = object.__new__(ProfanityCensor)
        censor.padding_before_ms = 200
        censor.padding_after_ms = 75

        expression = censor._build_interval_expr([{"start": 1.0, "end": 2.0}])

        self.assertEqual(expression, "between(t,0.8,2.075)")

    def test_7_1_filter_drops_only_front_center(self):
        censor = object.__new__(ProfanityCensor)
        censor.get_audio_stream_info = MagicMock(return_value=(8, "7.1"))

        graph = censor.generate_karaoke_filter_complex([{"start": 1.0, "end": 2.0}])

        self.assertIn(
            "pan=7.1|c0=c0|c1=c1|c2=0*c2|c3=c3|c4=c4|c5=c5|c6=c6|c7=c7",
            graph,
        )

    def test_5_1_transcription_uses_extracted_center_channel(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            censor = object.__new__(ProfanityCensor)
            model = MagicMock()
            model.transcribe.return_value = (iter(()), MagicMock())
            censor._shared_model = (model, "cpu")
            censor.input_file = "input.mkv"
            censor.model_name = "large"
            censor.whisper_library = "faster-whisper"
            censor.transcripts_dir = temporary_directory
            censor.used_cached_transcript = False
            censor.get_media_duration_seconds = MagicMock(return_value=60.0)
            censor.has_discrete_center_audio = MagicMock(return_value=True)
            censor.extract_center_channel = MagicMock(return_value="center.wav")

            with patch("backend.censor.engine.record_transcription_timing"):
                transcript = censor.transcribe_with_timestamps()

        model.transcribe.assert_called_once()
        self.assertEqual(model.transcribe.call_args.args[0], "center.wav")
        self.assertEqual(transcript["audio_source"], "front_center")

    def test_existing_compatible_transcript_skips_model_transcription(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            transcript_path = Path(temporary_directory) / "movie-transcript.json"
            transcript = {
                "text": "hello",
                "words": [{"word": "hello", "start": 0.0, "end": 0.5}],
                "audio_source": "full_mix",
                "whisper_library": "faster-whisper",
                "whisper_model": "large",
            }
            transcript_path.write_text(json.dumps(transcript), encoding="utf-8")
            censor = object.__new__(ProfanityCensor)
            censor.input_file = "movie.mkv"
            censor.model_name = "large"
            censor.whisper_library = "faster-whisper"
            censor.transcripts_dir = temporary_directory
            censor.used_cached_transcript = False
            censor.has_discrete_center_audio = MagicMock(return_value=False)
            censor._load_whisper_model = MagicMock()

            loaded = censor.transcribe_with_timestamps()

        self.assertEqual(loaded, transcript)
        self.assertTrue(censor.used_cached_transcript)
        censor._load_whisper_model.assert_not_called()

    def test_transcription_reports_live_progress_bar(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            censor = object.__new__(ProfanityCensor)
            model = MagicMock()
            word = MagicMock(word="hello", start=29.0, end=30.0)
            segment = MagicMock(text=" hello", words=[word], start=29.0, end=30.0)
            model.transcribe.return_value = (iter([segment]), MagicMock())
            censor._shared_model = (model, "cpu")
            censor.input_file = "input.mkv"
            censor.model_name = "large"
            censor.whisper_library = "faster-whisper"
            censor.transcripts_dir = temporary_directory
            censor.used_cached_transcript = False
            censor.get_media_duration_seconds = MagicMock(return_value=60.0)
            censor.has_discrete_center_audio = MagicMock(return_value=False)

            output = io.StringIO()
            with (
                patch("backend.censor.engine.record_transcription_timing"),
                patch("backend.censor.engine.time.perf_counter", side_effect=[100.0, 110.0, 120.0]),
                patch("backend.censor.engine.sys.stdout", output),
            ):
                censor.transcribe_with_timestamps()

        self.assertIn("[Whisper] [############------------]  50%", output.getvalue())
        self.assertIn("speed 3.00x", output.getvalue())
        self.assertIn("[Whisper] [########################] 100%", output.getvalue())

    def create_surround_censor(self):
        censor = object.__new__(ProfanityCensor)
        censor.input_file = "input.mkv"
        censor.output_file = "output.mkv"
        censor.censor_method = "mute"
        censor.ffmpeg_bin = "ffmpeg"
        censor.video_encoder = "libx264"
        censor.encoders = {"libx264"}
        censor.has_discrete_center_audio = MagicMock(return_value=True)
        censor.get_audio_stream_info = MagicMock(return_value=(6, "5.1"))
        censor.is_audio_only = MagicMock(return_value=False)
        censor.get_video_codec = MagicMock(return_value="h264")
        censor.get_media_duration_seconds = MagicMock(return_value=60.0)
        return censor

    def test_5_1_downmix_occurs_after_center_channel_censorship(self):
        censor = self.create_surround_censor()
        censor.surround_output = "downmix_stereo"

        completed = MagicMock(returncode=0, stderr="")
        with patch("backend.censor.engine.run_ffmpeg_with_progress", return_value=completed) as run:
            success = censor.censor_video([{"start": 1.0, "end": 2.0}])

        self.assertTrue(success)
        command = run.call_args.args[0]
        self.assertIn("-filter_complex", command)
        self.assertEqual(command[command.index("-ac") + 1], "2")
        self.assertLess(command.index("-filter_complex"), command.index("-ac"))

    def test_5_1_output_preserves_surround_layout_when_requested(self):
        censor = self.create_surround_censor()
        censor.surround_output = "preserve_5_1"

        completed = MagicMock(returncode=0, stderr="")
        with patch("backend.censor.engine.run_ffmpeg_with_progress", return_value=completed) as run:
            success = censor.censor_video([{"start": 1.0, "end": 2.0}])

        self.assertTrue(success)
        self.assertNotIn("-ac", run.call_args.args[0])

    def test_preserve_source_video_uses_stream_copy(self):
        censor = self.create_surround_censor()
        censor.has_discrete_center_audio.return_value = False
        censor.get_video_codec.return_value = "hevc"
        censor.video_mode = "preserve_source"

        completed = MagicMock(returncode=0, stderr="")
        with patch("backend.censor.engine.run_ffmpeg_with_progress", return_value=completed) as run:
            success = censor.censor_video([{"start": 1.0, "end": 2.0}])

        self.assertTrue(success)
        command = run.call_args.args[0]
        self.assertEqual(command[command.index("-c:v") + 1], "copy")

    def test_5_1_cache_requires_center_channel_transcript(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            transcript_path = Path(temporary_directory) / "episode-transcript.json"
            transcript_path.write_text('{"text": "", "words": []}')

            with patch("backend.censor.engine.probe_audio_stream", return_value=(6, "5.1")):
                self.assertFalse(
                    transcript_cache_is_compatible("episode.mkv", str(transcript_path), "ffprobe")
                )

            transcript_path.write_text(
                '{"text": "", "words": [], "audio_source": "front_center"}'
            )
            with patch("backend.censor.engine.probe_audio_stream", return_value=(6, "5.1")):
                self.assertTrue(
                    transcript_cache_is_compatible("episode.mkv", str(transcript_path), "ffprobe")
                )

    def test_zero_word_transcript_is_valid(self):
        transcript = validate_transcript_data(
            {
                "text": "",
                "words": [],
                "audio_source": "full_mix",
                "whisper_library": "faster-whisper",
                "whisper_model": "large",
            },
            whisper_library="faster-whisper",
            whisper_model="large",
        )

        self.assertEqual(transcript["words"], [])

    def test_malformed_word_timestamps_do_not_validate(self):
        with self.assertRaisesRegex(TranscriptValidationError, "timestamps"):
            validate_transcript_data(
                {
                    "text": "hello",
                    "words": [{"word": "hello", "start": 2.0, "end": 1.0}],
                    "audio_source": "full_mix",
                }
            )

    def test_atomic_transcript_failure_preserves_prior_artifact(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            transcript_path = Path(temporary_directory) / "movie-transcript.json"
            transcript_path.write_text("prior transcript", encoding="utf-8")
            transcript = {
                "text": "",
                "words": [],
                "audio_source": "full_mix",
                "whisper_library": "faster-whisper",
                "whisper_model": "large",
            }

            with (
                patch("backend.censor.engine.os.replace", side_effect=OSError("disk is read-only")),
                self.assertRaisesRegex(TranscriptValidationError, "saved and verified"),
            ):
                write_transcript_atomic(
                    transcript_path,
                    transcript,
                    whisper_library="faster-whisper",
                    whisper_model="large",
                    require_front_center=False,
                )

            self.assertEqual(transcript_path.read_text(encoding="utf-8"), "prior transcript")
            self.assertEqual(list(transcript_path.parent.glob("*.tmp")), [])

    def create_gated_pipeline(self, transcript_path: Path, transcription_result):
        censor = object.__new__(ProfanityCensor)
        censor.get_transcript_path = MagicMock(return_value=str(transcript_path))
        censor.estimate_processing_seconds = MagicMock(
            return_value={"total": 0.0, "transcribe": 0.0, "detect": 0.0, "censor": 0.0, "source": "test"}
        )
        if isinstance(transcription_result, Exception):
            censor.transcribe_with_timestamps = MagicMock(side_effect=transcription_result)
        else:
            censor.transcribe_with_timestamps = MagicMock(return_value=transcription_result)
        censor.whisper_library = "faster-whisper"
        censor.model_name = "large"
        censor.has_discrete_center_audio = MagicMock(return_value=False)
        censor.find_review_candidates = MagicMock(return_value=[])
        censor.detect_profanity = MagicMock(return_value=[])
        censor.report_potential_profanity = MagicMock()
        censor.censor_video = MagicMock(return_value=True)
        censor.last_error = None
        return censor

    def test_unsaved_in_memory_transcript_never_unlocks_transcoding(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            transcript_path = Path(temporary_directory) / "missing-transcript.json"
            valid_in_memory = {
                "text": "",
                "words": [],
                "audio_source": "full_mix",
                "whisper_library": "faster-whisper",
                "whisper_model": "large",
            }
            censor = self.create_gated_pipeline(transcript_path, valid_in_memory)

            success = censor.process()

        self.assertFalse(success)
        censor.censor_video.assert_not_called()
        self.assertIn("No such file", censor.last_error)

    def test_malformed_persisted_transcript_never_unlocks_transcoding(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            transcript_path = Path(temporary_directory) / "movie-transcript.json"
            malformed = {
                "text": "hello",
                "words": [{"word": "hello"}],
                "audio_source": "full_mix",
                "whisper_library": "faster-whisper",
                "whisper_model": "large",
            }
            transcript_path.write_text(json.dumps(malformed), encoding="utf-8")
            censor = self.create_gated_pipeline(transcript_path, malformed)

            success = censor.process()

        self.assertFalse(success)
        censor.censor_video.assert_not_called()
        self.assertIn("timestamps", censor.last_error)

    def test_transcription_failure_never_invokes_transcoding(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            transcript_path = Path(temporary_directory) / "movie-transcript.json"
            censor = self.create_gated_pipeline(
                transcript_path,
                RuntimeError("Whisper could not transcribe the file"),
            )

            success = censor.process()

        self.assertFalse(success)
        censor.censor_video.assert_not_called()
        self.assertIn("Whisper could not transcribe", censor.last_error)

    def test_verified_zero_word_transcript_unlocks_transcoding(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            transcript_path = Path(temporary_directory) / "movie-transcript.json"
            transcript = {
                "text": "",
                "words": [],
                "audio_source": "full_mix",
                "whisper_library": "faster-whisper",
                "whisper_model": "large",
            }
            transcript_path.write_text(json.dumps(transcript), encoding="utf-8")
            censor = self.create_gated_pipeline(transcript_path, transcript)

            success = censor.process()

        self.assertTrue(success)
        censor.censor_video.assert_called_once_with([])

    def test_force_retranscription_bypasses_the_cached_transcript_path(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            transcript_path = Path(temporary_directory) / "movie-transcript.json"
            transcript = {
                "text": "",
                "words": [],
                "audio_source": "full_mix",
                "whisper_library": "faster-whisper",
                "whisper_model": "large",
            }
            transcript_path.write_text(json.dumps(transcript), encoding="utf-8")
            censor = self.create_gated_pipeline(transcript_path, transcript)

            success = censor.process(report_only=True, force_transcribe=True)

        self.assertTrue(success)
        censor.transcribe_with_timestamps.assert_called_once_with(force=True)
        censor.censor_video.assert_not_called()

    def test_encoder_preference(self):
        self.assertEqual(select_video_encoder({"libx264", "h264_nvenc"}), "h264_nvenc")
        self.assertEqual(select_video_encoder({"libx264", "h264_qsv"}), "h264_qsv")
        self.assertEqual(select_video_encoder({"libx264"}), "libx264")

    def test_encoder_override_is_validated(self):
        self.assertEqual(select_video_encoder({"libx264"}, "libx264"), "libx264")
        with self.assertRaises(ValueError):
            select_video_encoder({"libx264"}, "h264_nvenc")

    def test_working_encoder_preserves_preference(self):
        with patch(
            "backend.runtime.environment.video_encoder_runtime_available",
            side_effect=lambda *arguments: arguments[1] in {"h264_qsv", "libx264"},
        ):
            encoder = select_working_video_encoder(
                "ffmpeg",
                {"h264_nvenc", "h264_qsv", "libx264"},
            )
        self.assertEqual(encoder, "h264_qsv")

    def test_working_encoder_skips_unusable_hardware(self):
        with patch(
            "backend.runtime.environment.video_encoder_runtime_available",
            side_effect=lambda *arguments: arguments[1] == "libx264",
        ):
            encoder = select_working_video_encoder(
                "ffmpeg",
                {"h264_nvenc", "h264_qsv", "libx264"},
            )
        self.assertEqual(encoder, "libx264")

    def test_paths_are_project_relative_and_creatable(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            with patch.dict(os.environ, {"CENSOR_PROJECT_ROOT": temporary_directory}):
                paths = get_runtime_paths()
                paths.create()
            self.assertEqual(paths.root, Path(temporary_directory).resolve())
            self.assertTrue(paths.ready.is_dir())
            self.assertTrue(paths.finished.is_dir())
            self.assertEqual(paths.transcoded, paths.finished)
            self.assertTrue(paths.transcripts.is_dir())

    def test_windows_winget_package_install_is_discoverable(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            package_root = (
                Path(temporary_directory)
                / "Microsoft"
                / "WinGet"
                / "Packages"
                / "Gyan.FFmpeg.Shared_Microsoft.Winget.Source_8wekyb3d8bbwe"
                / "ffmpeg-9.0.1-full_build-shared"
                / "bin"
            )
            package_root.mkdir(parents=True)
            (package_root / "ffmpeg.exe").write_text("")
            (package_root / "ffprobe.exe").write_text("")

            with patch.dict(os.environ, {"LOCALAPPDATA": temporary_directory}, clear=False):
                with patch("backend.runtime.environment.shutil.which", return_value=None):
                    with patch(
                        "backend.runtime.environment.subprocess.run",
                        return_value=MagicMock(returncode=0, stdout="ffmpeg version 9.0.1", stderr=""),
                    ):
                        self.assertEqual(find_ffmpeg(), str(package_root / "ffmpeg.exe"))
                        self.assertEqual(find_ffprobe(), str(package_root / "ffprobe.exe"))

    def test_ensure_executable_directory_on_path_prepends_once(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            executable = Path(temporary_directory) / "bin" / "ffmpeg.exe"
            executable.parent.mkdir(parents=True)
            executable.write_text("")
            initial_path = os.pathsep.join(["C:\\existing\\one", "C:\\existing\\two"])

            with patch.dict(os.environ, {"PATH": initial_path}, clear=False):
                ensure_executable_directory_on_path(str(executable))
                first_path = os.environ["PATH"]
                ensure_executable_directory_on_path(str(executable))
                second_path = os.environ["PATH"]

            expected_prefix = str(executable.parent.resolve())
            self.assertTrue(first_path.startswith(expected_prefix + os.pathsep))
            self.assertEqual(first_path, second_path)

    def test_whisper_cache_dir_defaults_to_repo_relative_folder(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "config.ini"
            config_path.write_text("[Whisper]\nCacheFolder = whisper-cache\n")
            cache_dir = get_whisper_cache_dir(Path(temporary_directory))
            self.assertEqual(cache_dir, (Path(temporary_directory) / "whisper-cache").resolve())

    def test_whisper_cache_dir_honors_environment_override(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            override = Path(temporary_directory) / "custom-cache"
            with patch.dict(os.environ, {"CENSOR_WHISPER_CACHE_DIR": str(override)}, clear=False):
                self.assertEqual(get_whisper_cache_dir(Path(temporary_directory)), override.resolve())

    def test_transcription_timing_uses_recent_matching_profile_median(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            with patch(
                "backend.runtime.environment.get_whisper_profile_key",
                return_value="large:cpu:int8",
            ):
                record_transcription_timing(100.0, 200.0, root=root)
                record_transcription_timing(100.0, 400.0, root=root)
                record_transcription_timing(100.0, 300.0, root=root)
                factor = get_calibrated_transcription_factor(root=root)
            self.assertEqual(factor, 3.0)

    def test_whisper_uses_cpu_when_cuda_is_unavailable(self):
        with patch("backend.runtime.environment.ctranslate2", None):
            status = get_whisper_device_status()
        self.assertEqual(status.selected, "cpu")
        self.assertEqual(status.compute_type, "int8")

    def test_persisted_whisper_device_is_used_without_environment_override(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("backend.runtime.environment.ctranslate2", None),
        ):
            status = get_whisper_device_status(requested_device="cuda")
        self.assertEqual(status.requested, "cuda")
        self.assertIn("explicitly requested", status.detail)

    def test_whisper_device_environment_override_takes_precedence(self):
        with (
            patch.dict(os.environ, {"CENSOR_WHISPER_DEVICE": "cpu"}, clear=False),
            patch("backend.runtime.environment.ctranslate2", None),
        ):
            status = get_whisper_device_status(requested_device="cuda")
        self.assertEqual(status.requested, "cpu")

    def test_whisper_model_validation_normalizes_large_alias(self):
        self.assertEqual(require_whisper_model("large"), "large-v3")
        self.assertEqual(require_whisper_model("small"), "small")
        with self.assertRaises(ValueError):
            require_whisper_model("not-a-model")

    def test_whisper_uses_supported_cuda_type_with_sufficient_memory(self):
        ctranslate2 = MagicMock()
        ctranslate2.get_cuda_device_count.return_value = 1
        ctranslate2.get_supported_compute_types.return_value = {"float16", "int8"}
        with (
            patch("backend.runtime.environment.ctranslate2", ctranslate2),
            patch("backend.runtime.environment.get_cuda_memory_mib", return_value=12288),
        ):
            status = get_whisper_device_status("large")
        self.assertEqual(status.selected, "cuda")
        self.assertEqual(status.compute_type, "float16")

    def test_whisper_uses_cpu_when_gpu_memory_is_insufficient_for_model(self):
        ctranslate2 = MagicMock()
        ctranslate2.get_cuda_device_count.return_value = 1
        ctranslate2.get_supported_compute_types.return_value = {"int8_float32", "int8"}
        with (
            patch("backend.runtime.environment.ctranslate2", ctranslate2),
            patch("backend.runtime.environment.get_cuda_memory_mib", return_value=4096),
        ):
            status = get_whisper_device_status("large")
        self.assertEqual(status.selected, "cpu")
        self.assertEqual(status.compute_type, "int8")

    def test_profanity_exclusions_load_from_configured_file(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "config.ini").write_text("[Profanity]\nExclusionsFile = policy.txt\n")
            (root / "policy.txt").write_text("# Keep these words\nFart\nugly # contextual\n\n")

            exclusions_file = get_profanity_exclusions_file(root)
            self.assertEqual(load_profanity_exclusions(exclusions_file), {"fart", "ugly"})

    def test_profanity_exclusions_honor_environment_override(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            override = root / "custom-policy.txt"
            override.write_text("snuff\n")

            with patch.dict(os.environ, {"CENSOR_EXCLUSIONS_FILE": str(override)}, clear=False):
                self.assertEqual(get_profanity_exclusions_file(root), override.resolve())

    def test_profanity_censor_words_load_from_configured_file(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "config.ini").write_text("[Profanity]\nCensorWordsFile = source.txt\n")
            (root / "source.txt").write_text("# Strong terms\nFuck\nshit # keep\n\n")

            censor_words_file = get_profanity_censor_words_file(root)
            self.assertEqual(load_profanity_censor_words(censor_words_file), {"fuck", "shit"})

    def test_profanity_censor_words_honor_environment_override(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            override = root / "custom-source.txt"
            override.write_text("fuck\n")

            with patch.dict(os.environ, {"CENSOR_CENSOR_WORDS_FILE": str(override)}, clear=False):
                self.assertEqual(get_profanity_censor_words_file(root), override.resolve())

    def test_review_candidates_exclude_current_policy_and_restore_it(self):
        censor = object.__new__(ProfanityCensor)
        censor.censor_words = {"fuck"}
        censor.exclude_words = {"ugly"}
        profanity.load_censor_words(list(censor.censor_words))

        candidates = censor.find_review_candidates(
            {
                "words": [
                    {"word": "fuck", "start": 0.0, "end": 0.5},
                    {"word": "weirdo", "start": 1.0, "end": 1.5},
                    {"word": "ugly", "start": 2.0, "end": 2.5},
                ]
            }
        )

        self.assertEqual(candidates, [{"word": "weirdo", "start": 1.0, "end": 1.5}])
        self.assertTrue(profanity.contains_profanity("fuck"))
        self.assertFalse(profanity.contains_profanity("weirdo"))

    def test_undiscovered_matches_are_only_censored_when_requested(self):
        censor = object.__new__(ProfanityCensor)
        censor.censor_words = {"fuck"}
        censor.exclude_words = {"ugly"}
        words_data = {
            "words": [
                {"word": "fuck", "start": 0.0, "end": 0.5},
                {"word": "weirdo", "start": 1.0, "end": 1.5},
                {"word": "ugly", "start": 2.0, "end": 2.5},
            ]
        }
        profanity.load_censor_words(list(censor.censor_words))

        self.assertEqual([item["word"] for item in censor.detect_profanity(words_data)], ["fuck"])
        self.assertEqual(
            [item["word"] for item in censor.detect_profanity(words_data, include_undiscovered=True)],
            ["fuck", "weirdo"],
        )
        self.assertTrue(profanity.contains_profanity("fuck"))
        self.assertFalse(profanity.contains_profanity("weirdo"))

    def test_configured_words_do_not_depend_on_shared_vendor_dictionary_state(self):
        censor = object.__new__(ProfanityCensor)
        censor.censor_words = {"customterm"}
        censor.exclude_words = set()
        censor.profanity = profanity
        profanity.load_censor_words()

        detected = censor.detect_profanity(
            {"words": [{"word": "customterm", "start": 1.0, "end": 1.4}]}
        )

        self.assertEqual([item["word"] for item in detected], ["customterm"])


if __name__ == "__main__":
    unittest.main()
