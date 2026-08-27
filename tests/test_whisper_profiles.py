import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from backend.censor import transcript_cache_is_compatible
from backend.runtime.dependencies import build_install_plan
from backend.runtime.environment import require_whisper_model
from backend.runtime.transcription import transcribe_segments
from backend.settings import AppSettings, settings_from_dict, settings_to_dict


class WhisperProfileTests(unittest.TestCase):
    def test_settings_default_to_faster_whisper_large_v3(self):
        settings = AppSettings.defaults()

        self.assertEqual(settings.whisper.library, "faster-whisper")
        self.assertEqual(settings.whisper.model, "large-v3")

    def test_library_and_smaller_model_round_trip(self):
        defaults = AppSettings.defaults()
        configured = replace(
            defaults,
            whisper=replace(defaults.whisper, library="openai-whisper", model="small"),
        )

        restored = settings_from_dict(settings_to_dict(configured))

        self.assertEqual(restored.whisper, configured.whisper)

    def test_legacy_large_alias_is_normalized(self):
        self.assertEqual(require_whisper_model("large"), "large-v3")

    def test_install_plan_targets_selected_library_and_model(self):
        plan = build_install_plan(
            ["python", "whisper_model"],
            python_executable=Path("C:/Python/python.exe"),
            cache_dir=Path("C:/models"),
            whisper_library="openai-whisper",
            whisper_model="small",
        )

        self.assertIn("openai-whisper==20250625", plan.actions[0].command)
        self.assertEqual(plan.actions[1].dependency_ids, ("whisper:openai-whisper:small",))
        self.assertEqual(plan.actions[1].command[-4:], ("--library", "openai-whisper", "--model", "small"))

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

    def test_openai_segments_are_normalized(self):
        class Model:
            def transcribe(self, _path, **_options):
                return {
                    "segments": [
                        {
                            "text": " hello",
                            "start": 0,
                            "end": 1,
                            "words": [{"word": " hello", "start": 0.1, "end": 0.8}],
                        }
                    ]
                }

        segments = list(transcribe_segments(Model(), "openai-whisper", "clip.wav"))

        self.assertEqual(segments[0]["words"][0]["word"], " hello")


if __name__ == "__main__":
    unittest.main()
