import hashlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import MagicMock, patch

from backend.censor.engine import ProfanityCensor
from backend.filesystem.paths import RootBinding
from backend.filesystem.publication import Publication
from backend.jobs.media import legacy_output_path, output_path, transcript_path
from backend.media_identity import (
    MediaIdentityError, hash_stream, publish_output, provenance_path,
    require_identity, verified_source, verify_finished,
)
from backend.service.library import scan_library
from backend.settings import AppSettings, DirectorySettings
from tests.media_fixtures import identity, provenance


class MediaIdentityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "film.mkv"
        self.source.write_bytes(b"source")
        self.transcripts = self.root / "transcripts"
        self.transcripts.mkdir()

    def censor(self):
        censor = object.__new__(ProfanityCensor)
        censor.input_file = str(self.source)
        censor.output_file = str(self.root / "output.mkv")
        censor.transcripts_dir = str(self.transcripts)
        censor.whisper_library = "faster-whisper"
        censor.model_name = "large-v3"
        censor.cancellation = Event()
        censor.progress_callback = MagicMock()
        censor.has_discrete_center_audio = MagicMock(return_value=False)
        censor.get_media_duration_seconds = MagicMock(return_value=0)
        censor.estimate_processing_seconds = MagicMock(return_value={"total": 0})
        censor.validate_transcription_audio = MagicMock()
        model = MagicMock()
        model.transcribe.side_effect = lambda *_args, **_kwargs: (iter(()), MagicMock())
        censor._shared_model = (model, "cpu")
        censor.find_review_candidates = MagicMock(return_value=[])
        censor.detect_profanity = MagicMock(return_value=[])
        censor.report_potential_profanity = MagicMock()
        censor.censor_video = MagicMock(return_value=True)
        censor.censor_method = "mute"
        censor.padding_before_ms = censor.padding_after_ms = 150
        censor.surround_output = "preserve_5_1"
        censor.video_mode = "preserve_source"
        censor.censor_words = {"synthetic"}
        censor.exclude_words = set()
        return censor

    def transcript(self, source_identity=None):
        path = transcript_path(self.source, self.transcripts)
        path.write_text(json.dumps({
            "text": "", "words": [], "audio_source": "full_mix",
            "whisper_library": "faster-whisper", "whisper_model": "large-v3",
            "source_identity": source_identity or identity(),
        }), encoding="utf-8")
        return path

    def test_sha256_known_vector_empty_file_and_cancellation(self):
        self.assertEqual(hash_stream(io.BytesIO(b"abc")),
                         "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
        self.assertEqual(hash_stream(io.BytesIO(b"")), hashlib.sha256(b"").hexdigest())
        cancelled = Event()
        def progress(_):
            cancelled.set()
        with self.assertRaises(InterruptedError):
            hash_stream(io.BytesIO(b"x" * (2 * 1024 * 1024)), cancellation=cancelled, progress=progress)
        with self.assertRaises(InterruptedError):
            hash_stream(io.BytesIO(b"abc"), cancellation=cancelled)

    def test_same_size_and_timestamp_replacement_is_detected(self):
        transcript = self.transcript()
        original_transcript = transcript.read_bytes()
        stamp = self.source.stat()
        self.source.write_bytes(b"change")
        os.utime(self.source, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        censor = self.censor()
        self.assertFalse(censor.process_verified_transcript())
        censor.censor_video.assert_not_called()
        censor._shared_model[0].transcribe.assert_not_called()
        self.assertIn("do not match", censor.last_error)
        self.assertEqual(transcript.read_bytes(), original_transcript)
        self.assertEqual(self.source.read_bytes(), b"change")

    def test_rename_keeps_identity_and_output_names_omit_the_source_container(self):
        with verified_source(self.source) as before:
            pass
        relocated = self.root / "renamed.mp4"
        self.source.rename(relocated)
        with verified_source(relocated) as after:
            self.assertEqual(before, after)
        other = self.source.with_suffix(".mp4")
        self.assertNotEqual(transcript_path(self.source, self.transcripts), transcript_path(other, self.transcripts))
        self.assertEqual(output_path(self.source, self.root).name, "film-censored.mkv")
        self.assertEqual(output_path(self.source, self.root), output_path(other, self.root))
        self.assertEqual(legacy_output_path(other, self.root).name, "film.mp4-censored.mkv")

    def test_source_is_pinned_until_processing_finishes(self):
        with verified_source(self.source):
            with self.assertRaises(OSError):
                self.source.write_bytes(b"changed")
            with self.assertRaises(OSError):
                self.source.rename(self.root / "moved.mkv")
        self.assertEqual(self.source.read_bytes(), b"source")

    def test_process_hashes_once_and_rehashes_on_later_use(self):
        self.transcript()
        censor = self.censor()
        with patch("backend.media_identity.hash_stream", wraps=hash_stream) as hashing:
            self.assertTrue(censor.process(report_only=True))
            self.assertEqual(hashing.call_count, 1)
            self.assertTrue(censor.process_verified_transcript())
            self.assertEqual(hashing.call_count, 2)
        censor._shared_model[0].transcribe.assert_not_called()
        self.assertEqual(censor.output_provenance["source_identity"], identity())

    def test_legacy_is_preserved_and_requires_explicit_fresh_transcription(self):
        legacy = self.transcripts / "film-transcript.json"
        legacy.write_bytes(b"legacy contents")
        censor = self.censor()
        self.assertFalse(censor.process(report_only=True))
        censor._shared_model[0].transcribe.assert_not_called()
        with patch("backend.censor.engine.record_transcription_timing"):
            self.assertTrue(censor.process(report_only=True, force_transcribe=True))
        self.assertEqual(legacy.read_bytes(), b"legacy contents")
        data = json.loads(Path(censor.get_transcript_path()).read_text())
        self.assertEqual(data["source_identity"], identity())
        self.assertEqual(self.source.read_bytes(), b"source")

    def test_explicit_retranscription_retains_previous_transcript(self):
        transcript = self.transcript()
        previous = transcript.read_bytes()
        with patch("backend.censor.engine.record_transcription_timing"):
            self.assertTrue(self.censor().process(report_only=True, force_transcribe=True))
        history = list((self.transcripts / ".history").iterdir())
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].read_bytes(), previous)

    def test_batch_four_retranscription_uses_normalized_words_and_keeps_history(self):
        transcript = self.transcript()
        previous = transcript.read_bytes()
        censor = self.censor()
        censor.transcription_batch_size = 4
        segments = [{
            "text": " Example", "start": 1.0, "end": 1.5,
            "words": [{"word": " Example", "start": 1.1, "end": 1.4}],
        }]
        with patch("backend.censor.engine.transcribe_segments", return_value=iter(segments)) as transcribe, \
             patch("backend.censor.engine.record_transcription_timing"):
            self.assertTrue(censor.process(report_only=True, force_transcribe=True))
        self.assertEqual(transcribe.call_args.kwargs["experimental_batch_size"], 4)
        self.assertTrue(callable(transcribe.call_args.kwargs["check_cancelled"]))
        result = json.loads(transcript.read_text(encoding="utf-8"))
        self.assertEqual(result["words"][0]["start"], 1.1)
        self.assertEqual(result["source_identity"], identity())
        self.assertEqual(next((self.transcripts / ".history").iterdir()).read_bytes(), previous)
        self.assertEqual(self.source.read_bytes(), b"source")

    def test_batch_four_reuses_existing_verified_transcript_without_inference(self):
        transcript = self.transcript()
        previous = transcript.read_bytes()
        censor = self.censor()
        censor.transcription_batch_size = 4
        with patch("backend.censor.engine.transcribe_segments") as transcribe:
            self.assertTrue(censor.process(report_only=True))
        transcribe.assert_not_called()
        self.assertEqual(transcript.read_bytes(), previous)

    def test_batch_failure_does_not_replace_previous_transcript_or_retry(self):
        transcript = self.transcript()
        previous = transcript.read_bytes()
        censor = self.censor()
        censor.transcription_batch_size = 4
        with patch("backend.censor.engine.transcribe_segments", side_effect=RuntimeError("out of memory")) as transcribe:
            self.assertFalse(censor.process(report_only=True, force_transcribe=True))
        self.assertIn("out of memory", censor.last_error)
        transcribe.assert_called_once()
        self.assertEqual(transcript.read_bytes(), previous)
        self.assertEqual(self.source.read_bytes(), b"source")

    def test_cancellation_after_last_segment_prevents_publication(self):
        transcript = self.transcript()
        previous = transcript.read_bytes()
        censor = self.censor()
        censor.transcription_batch_size = 4

        def segments(*_args, **_kwargs):
            censor.cancellation.set()
            return iter(())

        with patch("backend.censor.engine.transcribe_segments", side_effect=segments):
            self.assertFalse(censor.process(report_only=True, force_transcribe=True))
        self.assertIn("cancelled", censor.last_error)
        self.assertEqual(transcript.read_bytes(), previous)
        self.assertEqual(self.source.read_bytes(), b"source")

    def test_isolated_worker_cancel_closes_before_surround_temporary_is_removed(self):
        censor = self.censor()
        censor.transcription_batch_size = 4
        censor.isolate_transcription = True
        censor.whisper_cache_dir = self.root
        censor.whisper_device = "cpu"
        censor.has_discrete_center_audio.return_value = True
        temporary_audio = self.root / "center.wav"
        temporary_audio.write_bytes(b"audio")
        censor.extract_center_channel = MagicMock(return_value=str(temporary_audio))
        observed = []

        def worker(*_args, **_kwargs):
            try:
                yield {"text": " Example", "start": 1.0, "end": 1.5, "words": []}
            finally:
                observed.append(temporary_audio.exists())

        def progress(stage, *_args, **kwargs):
            if stage == "transcribing" and kwargs.get("message") == "Loading the speech model":
                censor.cancellation.set()

        censor._emit_progress = progress
        with patch("backend.censor.engine.transcribe_in_process", side_effect=worker):
            self.assertFalse(censor.process(report_only=True, force_transcribe=True))
        self.assertEqual(observed, [True])
        self.assertFalse(temporary_audio.exists())
        self.assertEqual(self.source.read_bytes(), b"source")

    def test_isolated_worker_failure_preserves_existing_transcript_and_source(self):
        transcript = self.transcript()
        previous = transcript.read_bytes()
        censor = self.censor()
        censor.transcription_batch_size = 4
        censor.isolate_transcription = True
        censor.whisper_cache_dir = self.root
        censor.whisper_device = "cpu"
        with patch("backend.censor.engine.transcribe_in_process", side_effect=RuntimeError("worker failed")) as worker:
            self.assertFalse(censor.process(report_only=True, force_transcribe=True))
        worker.assert_called_once()
        self.assertIn("worker failed", censor.last_error)
        self.assertEqual(transcript.read_bytes(), previous)
        self.assertEqual(self.source.read_bytes(), b"source")

    def test_isolated_worker_output_is_published_with_verified_identity(self):
        transcript = self.transcript()
        previous = transcript.read_bytes()
        censor = self.censor()
        censor.transcription_batch_size = 4
        censor.isolate_transcription = True
        censor.whisper_cache_dir = self.root
        censor.whisper_device = "cpu"
        segments = [{
            "text": " Example", "start": 1.0, "end": 1.5,
            "words": [{"word": " Example", "start": 1.1, "end": 1.4}],
        }]
        with patch("backend.censor.engine.transcribe_in_process", return_value=iter(segments)) as worker, \
             patch("backend.censor.engine.record_transcription_timing"):
            self.assertTrue(censor.process(report_only=True, force_transcribe=True))
        worker.assert_called_once()
        result = json.loads(transcript.read_text(encoding="utf-8"))
        self.assertEqual(result["words"][0]["start"], 1.1)
        self.assertEqual(result["source_identity"], identity())
        self.assertEqual(next((self.transcripts / ".history").iterdir()).read_bytes(), previous)
        self.assertEqual(self.source.read_bytes(), b"source")

    def test_isolated_transcription_emits_preparation_and_inference_statuses(self):
        censor = self.censor()
        censor.transcription_batch_size = 4
        censor.isolate_transcription = True
        censor.whisper_cache_dir = self.root
        censor.whisper_device = "cpu"
        def worker(*_args, **kwargs):
            kwargs["on_ready"]()
            kwargs["on_transcribing"]()
            yield {"text": " Example", "start": 1.0, "end": 1.5, "words": []}

        with patch("backend.censor.engine.transcribe_in_process", side_effect=worker), \
             patch("backend.censor.engine.record_transcription_timing"):
            self.assertTrue(censor.process(report_only=True, force_transcribe=True))
        events = [call.args[0] for call in censor.progress_callback.call_args_list]
        statuses = [(event["message"], event["percent"]) for event in events if event["stage"] == "transcribing"]
        self.assertEqual(statuses[:4], [
            ("Checking and preparing audio", None),
            ("Loading the speech model", None),
            ("Preparing audio for transcription", None),
            ("Transcribing audio", 0.0),
        ])

    def test_renamed_source_reuses_recorded_transcript_without_transcription(self):
        old = self.transcript()
        before = old.read_bytes()
        renamed = self.root / "renamed.mp4"
        self.source.rename(renamed)
        self.source = renamed
        censor = self.censor()
        self.assertTrue(censor.process(report_only=True))
        censor._shared_model[0].transcribe.assert_not_called()
        self.assertEqual(old.read_bytes(), before)
        self.assertEqual(json.loads(Path(censor.get_transcript_path()).read_text())["source_identity"], identity())

    def test_explicit_retranscription_can_repair_and_retain_an_empty_transcript(self):
        transcript_path(self.source, self.transcripts).touch()
        with patch("backend.censor.engine.record_transcription_timing"):
            self.assertTrue(self.censor().process(report_only=True, force_transcribe=True))
        history = list((self.transcripts / ".history").iterdir())
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].read_bytes(), b"")

    def test_ambiguous_recorded_transcripts_require_a_decision(self):
        first = self.transcript()
        data = json.loads(first.read_text())
        data["text"] = "a different transcript"
        (self.transcripts / "other.mp4-transcript.json").write_text(json.dumps(data))
        self.source = self.source.rename(self.root / "renamed.mp4")
        censor = self.censor()
        self.assertFalse(censor.process(report_only=True))
        self.assertIn("Multiple different transcripts", censor.last_error)
        censor._shared_model[0].transcribe.assert_not_called()

    def test_finished_provenance_detects_changed_media_and_wrong_source(self):
        output = self.root / "finished.mkv"
        output.write_bytes(b"finished")
        provenance(self.source, output)
        verify_finished(identity(), output)
        with self.assertRaises(MediaIdentityError):
            verify_finished(identity(b"change"), output)
        output.write_bytes(b"modified")
        with self.assertRaises(MediaIdentityError):
            verify_finished(identity(), output)

    def test_interrupted_sidecar_publication_keeps_media_and_blocks_unverified_use(self):
        output = self.root / "finished.mkv"
        censor = MagicMock(output_provenance=provenance(self.source))
        # Publication resolves Windows short paths before calling the failure hook.
        sidecar = provenance_path(output).resolve()
        original_publish = Publication.publish
        def interrupt_metadata(publication, verify):
            if publication.destination == sidecar:
                raise OSError("simulated interruption")
            return original_publish(publication, verify)
        with patch.object(Publication, "publish", interrupt_metadata):
            with self.assertRaisesRegex(OSError, "simulated interruption"), Publication(RootBinding.capture(self.root), output) as publication:
                publication.stage.write_bytes(b"finished")
                publish_output(publication, censor)
        self.assertEqual(output.read_bytes(), b"finished")
        self.assertEqual(self.source.read_bytes(), b"source")
        with self.assertRaises(OSError):
            verify_finished(identity(), output)
        with Publication(RootBinding.capture(self.root), output, overwrite=True) as publication:
            publication.stage.write_bytes(b"finished")
            publish_output(publication, censor)
        verify_finished(identity(), output)

    def test_library_does_not_hash_or_adopt_legacy_artifacts(self):
        folders = [self.root / name for name in ("input", "output", "archive", "records")]
        for folder in folders:
            folder.mkdir()
        source = folders[0] / "film.mkv"
        source.write_bytes(b"source")
        legacy = folders[3] / "film-transcript.json"
        legacy.write_bytes(b"legacy")
        settings = AppSettings(directories=DirectorySettings(*folders))
        with patch("backend.media_identity.hash_stream", side_effect=AssertionError("Polling hashed media")):
            items = scan_library(settings, ffprobe_bin="ffprobe")
        self.assertEqual(items[0].status, "unverified")
        self.assertIsNone(items[0].transcript)
        self.assertEqual(legacy.read_bytes(), b"legacy")

    def test_missing_and_malformed_identity_are_rejected(self):
        for actual in (None, {}, {"algorithm": "sha256", "digest": "short", "size_bytes": 6}):
            with self.subTest(actual=actual), self.assertRaises(MediaIdentityError):
                require_identity({"source_identity": actual}, identity())


if __name__ == "__main__":
    unittest.main()
