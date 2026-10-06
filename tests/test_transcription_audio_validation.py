"""Audio validation must distinguish missing metadata from missing samples."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.censor.engine import ProfanityCensor, TranscriptValidationError
from backend.runtime import resolve_media_tools


class TranscriptionAudioValidationTests(unittest.TestCase):
    def setUp(self):
        self.censor = object.__new__(ProfanityCensor)
        self.censor.ffprobe_bin = "ffprobe"
        self.censor.ffmpeg_bin = "ffmpeg"
        self.censor.input_file = "valid.mkv"

    def metadata(self, **fields):
        return MagicMock(returncode=0, stdout=json.dumps({
            "streams": [{"codec_name": "aac", "channels": 2, "sample_rate": "48000", **fields}],
            "format": {"duration": "1431.263"},
        }))

    def test_missing_or_inconclusive_duration_uses_bounded_decode(self):
        for fields in ({}, {"duration": None}, {"duration": "N/A"}, {"duration": "nan"},
                       {"duration": "inf"}, {"duration": "0"}, {"duration": "-1"}):
            with self.subTest(fields=fields), patch(
                "backend.censor.engine.subprocess.run",
                side_effect=[self.metadata(**fields), MagicMock(returncode=0, stdout=b"\0\0" * 16000)],
            ) as run:
                self.censor.validate_transcription_audio()
                decode = run.call_args_list[1]
                command = decode.args[0]
                self.assertEqual(command[0], "ffmpeg")
                self.assertEqual(command[command.index("-map") + 1], "0:a:0")
                self.assertEqual(command[command.index("-t") + 1], "1")
                self.assertEqual(command[command.index("-protocol_whitelist") + 1], "file,pipe")
                self.assertEqual(command[-1], "pipe:1")
                self.assertEqual(decode.kwargs["timeout"], 15)
                self.assertNotIn("text", decode.kwargs)

    def test_stream_duration_can_avoid_extra_decode(self):
        with patch("backend.censor.engine.subprocess.run", return_value=self.metadata(duration="12.5")) as run:
            self.censor.validate_transcription_audio()
        run.assert_called_once()

    def test_container_duration_does_not_hide_empty_or_corrupt_audio(self):
        for result in (MagicMock(returncode=0, stdout=b""), MagicMock(returncode=0, stdout=b"\0"),
                       MagicMock(returncode=1, stdout=b"\0\0")):
            with self.subTest(result=result), patch(
                "backend.censor.engine.subprocess.run", side_effect=[self.metadata(), result],
            ), self.assertRaisesRegex(TranscriptValidationError, "could not produce usable samples"):
                self.censor.validate_transcription_audio()

    def test_missing_or_malformed_streams_never_start_decode(self):
        for payload in ("[]", "{}", '{"streams": []}', '{"streams": [null]}', "not JSON",
                        '{"streams": [{"channels": "bad", "sample_rate": "48000"}]}'):
            with self.subTest(payload=payload), patch("backend.censor.engine.subprocess.run", return_value=MagicMock(
                returncode=0, stdout=payload,
            )) as run, self.assertRaisesRegex(TranscriptValidationError, "no usable audio stream"):
                self.censor.validate_transcription_audio()
            run.assert_called_once()

    def test_tool_failures_are_actionable_without_claiming_the_file_is_damaged(self):
        for phase in ("probe", "decode"):
            for error, expected in ((subprocess.TimeoutExpired("tool", 15), "then retry"),
                                    (OSError("cannot start"), "Check FFmpeg")):
                results = [error] if phase == "probe" else [self.metadata(), error]
                with self.subTest(phase=phase, error=error), patch(
                    "backend.censor.engine.subprocess.run", side_effect=results,
                ), self.assertRaisesRegex(TranscriptValidationError, expected):
                    self.censor.validate_transcription_audio()

    def test_selected_source_is_used_for_both_checks(self):
        with patch("backend.censor.engine.subprocess.run", side_effect=[
            self.metadata(), MagicMock(returncode=0, stdout=b"\0\0"),
        ]) as run:
            self.censor.validate_transcription_audio("selected.wav")
        self.assertEqual(run.call_args_list[0].args[0][-1], "selected.wav")
        self.assertIn("selected.wav", run.call_args_list[1].args[0])

    def test_real_silent_mkv_without_stream_duration_is_accepted_unchanged(self):
        ffmpeg, ffprobe = resolve_media_tools()
        if not ffmpeg or not ffprobe:
            self.skipTest("Local FFmpeg/FFprobe needed")
        self.censor.ffmpeg_bin, self.censor.ffprobe_bin = ffmpeg, ffprobe
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "silent.mkv"
            subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-f", "lavfi",
                            "-i", "anullsrc=r=48000:cl=stereo", "-t", "0.25", "-c:a", "aac", str(source)],
                           check=True, capture_output=True, timeout=15)
            before = source.read_bytes()
            self.censor.input_file = str(source)
            result = subprocess.run([ffprobe, "-v", "error", "-select_streams", "a:0",
                                     "-show_entries", "stream=duration", "-of", "json", str(source)],
                                    check=True, capture_output=True, text=True, timeout=15)
            self.assertNotIn("duration", json.loads(result.stdout)["streams"][0])
            self.censor.validate_transcription_audio()
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(list(Path(temporary).iterdir()), [source])


if __name__ == "__main__":
    unittest.main()
