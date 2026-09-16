import json
import subprocess
import unittest
from threading import Event
from unittest.mock import patch

from backend.censor.engine import ProfanityCensor


class OutputVerificationTests(unittest.TestCase):
    def create_censor(self):
        censor = ProfanityCensor.__new__(ProfanityCensor)
        censor.cancellation = Event()
        censor.ffprobe_bin = "ffprobe.exe"
        censor.output_file = "staged.partial.mkv"
        return censor

    def test_video_output_requires_both_audio_and_video_and_successful_probe(self):
        censor = self.create_censor()
        for streams, returncode in [(["audio"], 0), (["video"], 0), (["audio", "video"], 1), ([], 0)]:
            with self.subTest(streams=streams, returncode=returncode), \
                    patch.object(censor, "is_audio_only", return_value=False), \
                    patch("backend.censor.engine.subprocess.run", return_value=subprocess.CompletedProcess(
                        [], returncode, json.dumps({"streams": [{"codec_type": item} for item in streams]})
                    )):
                with self.assertRaises(RuntimeError):
                    censor.verify_output()

    def test_audio_output_does_not_require_a_video_stream(self):
        censor = self.create_censor()
        with patch.object(censor, "is_audio_only", return_value=True), \
                patch("backend.censor.engine.subprocess.run", return_value=subprocess.CompletedProcess(
                    [], 0, '{"streams":[{"codec_type":"audio"}]}'
                )):
            censor.verify_output()

    def test_unreadable_probe_result_is_rejected(self):
        censor = self.create_censor()
        with patch("backend.censor.engine.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "invalid")):
            with self.assertRaisesRegex(RuntimeError, "could not be verified"):
                censor.verify_output()
