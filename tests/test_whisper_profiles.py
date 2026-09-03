import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from backend.censor import transcript_cache_is_compatible
from backend.runtime.dependencies import DependencyPlanError, build_install_plan
from backend.runtime.environment import require_whisper_model
from backend.runtime.transcription import transcribe_segments
from backend.settings import AppSettings, settings_from_dict, settings_to_dict


class WhisperProfileTests(unittest.TestCase):
    def test_settings_default_to_faster_whisper_large_v3(self):
        settings = AppSettings.defaults()

        self.assertEqual(settings.whisper.library, "faster-whisper")
        self.assertEqual(settings.whisper.model, "large-v3")

    def test_retired_library_setting_migrates_to_faster_whisper(self):
        payload = settings_to_dict(AppSettings.defaults())
        payload["whisper"] = {"library": "openai-whisper", "model": "small"}

        restored = settings_from_dict(payload)

        self.assertEqual(restored.whisper.library, "faster-whisper")
        self.assertEqual(restored.whisper.model, "small")

    def test_legacy_large_alias_is_normalized(self):
        self.assertEqual(require_whisper_model("large"), "large-v3")

    def test_install_plan_rejects_retired_library(self):
        with self.assertRaisesRegex(DependencyPlanError, "Unsupported Whisper library"):
            build_install_plan(
                ["python", "whisper_model"],
                whisper_library="openai-whisper",
            )

    def test_transcript_cache_rejects_a_different_profile(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            transcript = Path(temporary_directory) / "clip-transcript.json"
            transcript.write_text(
                json.dumps(
                    {
                        "audio_source": "full_mix",
                        "whisper_library": "faster-whisper",
                        "whisper_model": "large-v3",
                    }
                ),
                encoding="utf-8",
            )
            with patch("backend.censor.engine.probe_audio_stream", return_value=(2, "stereo")):
                compatible = transcript_cache_is_compatible(
                    "clip.mp4",
                    str(transcript),
                    "ffprobe",
                    "openai-whisper",
                    "large-v3",
                )

        self.assertFalse(compatible)

    def test_retired_library_cannot_transcribe(self):
        with self.assertRaisesRegex(ValueError, "Unsupported Whisper library"):
            list(transcribe_segments(object(), "openai-whisper", "clip.wav"))


if __name__ == "__main__":
    unittest.main()
