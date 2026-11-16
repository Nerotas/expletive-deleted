import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.runtime.transcription import transcribe_segments


class BatchedTranscriptionTests(unittest.TestCase):
    def setUp(self):
        self.segment = SimpleNamespace(
            text=" Example", start=1.0, end=2.0,
            words=[SimpleNamespace(word=" Example", start=1.1, end=1.8)],
        )
        self.model = Mock()
        self.model.transcribe.return_value = (iter([self.segment]), None)

    def test_default_preserves_standard_options_and_shape(self):
        self.assertEqual(list(transcribe_segments(self.model, "faster-whisper", "clip.wav")), [{
            "text": " Example", "start": 1.0, "end": 2.0,
            "words": [{"word": " Example", "start": 1.1, "end": 1.8}],
        }])
        self.model.transcribe.assert_called_once_with(
            "clip.wav", language="en", word_timestamps=True, vad_filter=True,
            condition_on_previous_text=True, hallucination_silence_threshold=2.0,
        )

    def test_batch_modes_share_shape_but_not_unsupported_options(self):
        for size in (1, 2, 4):
            with self.subTest(size=size), patch("faster_whisper.BatchedInferencePipeline") as pipeline:
                pipeline.return_value.transcribe.return_value = (iter([self.segment]), None)
                result = list(transcribe_segments(
                    self.model, "faster-whisper", "clip.wav", experimental_batch_size=size,
                ))
                pipeline.assert_called_once_with(model=self.model)
                pipeline.return_value.transcribe.assert_called_once_with(
                    "clip.wav", language="en", word_timestamps=True, vad_filter=True, batch_size=size,
                )
                self.assertEqual(result[0]["words"][0]["start"], 1.1)
                self.model.transcribe.assert_not_called()

    def test_invalid_batch_sizes_never_start_inference(self):
        for size in (0, -1, 8, True, 1.5, "2"):
            with self.subTest(size=size), self.assertRaisesRegex(ValueError, "batch size"):
                list(transcribe_segments(self.model, "faster-whisper", "clip.wav", experimental_batch_size=size))
        self.model.transcribe.assert_not_called()

    def test_version_mismatch_is_explicit(self):
        with patch("importlib.metadata.version", return_value="1.3.0"):
            with self.assertRaisesRegex(RuntimeError, "requires faster-whisper 1.2.1"):
                list(transcribe_segments(self.model, "faster-whisper", "clip.wav", experimental_batch_size=1))
        self.model.transcribe.assert_not_called()

    def test_missing_word_timestamps_remain_empty(self):
        self.segment.words = None
        result = list(transcribe_segments(self.model, "faster-whisper", "clip.wav"))
        self.assertEqual(result[0]["words"], [])

    def test_pre_cancelled_does_not_start(self):
        check = Mock(side_effect=InterruptedError("Cancelled"))
        with self.assertRaises(InterruptedError):
            list(transcribe_segments(self.model, "faster-whisper", "clip.wav", check_cancelled=check))
        self.model.transcribe.assert_not_called()

    def test_cancel_during_decode_closes_iterator_before_yield(self):
        closed = []
        cancelled = False

        def segments():
            nonlocal cancelled
            try:
                cancelled = True
                yield self.segment
            finally:
                closed.append(True)

        def check():
            if cancelled:
                raise InterruptedError("Cancelled")

        self.model.transcribe.return_value = (segments(), None)
        with self.assertRaises(InterruptedError):
            list(transcribe_segments(self.model, "faster-whisper", "clip.wav", check_cancelled=check))
        self.assertEqual(closed, [True])

    def test_inference_failure_is_not_retried_or_changed_to_standard(self):
        with patch("faster_whisper.BatchedInferencePipeline") as pipeline:
            pipeline.return_value.transcribe.side_effect = RuntimeError("out of memory")
            with self.assertRaisesRegex(RuntimeError, "out of memory"):
                list(transcribe_segments(self.model, "faster-whisper", "clip.wav", experimental_batch_size=4))
            pipeline.return_value.transcribe.assert_called_once()
            self.model.transcribe.assert_not_called()

    def test_lazy_batch_failure_closes_stream_without_retry(self):
        closed = []

        def segments():
            try:
                yield self.segment
                raise RuntimeError("decoder failed")
            finally:
                closed.append(True)

        with patch("faster_whisper.BatchedInferencePipeline") as pipeline:
            pipeline.return_value.transcribe.return_value = (segments(), None)
            output = transcribe_segments(
                self.model, "faster-whisper", "clip.wav", experimental_batch_size=2,
            )
            self.assertEqual(next(output)["text"], self.segment.text)
            with self.assertRaisesRegex(RuntimeError, "decoder failed"):
                next(output)
            self.assertEqual(closed, [True])
            self.model.transcribe.assert_not_called()

    def test_early_consumer_close_releases_batch_stream(self):
        closed = []

        def segments():
            try:
                yield self.segment
                yield self.segment
            finally:
                closed.append(True)

        with patch("faster_whisper.BatchedInferencePipeline") as pipeline:
            pipeline.return_value.transcribe.return_value = (segments(), None)
            output = iter(transcribe_segments(
                self.model, "faster-whisper", "clip.wav", experimental_batch_size=1,
            ))
            next(output)
            output.close()
            self.assertEqual(closed, [True])


if __name__ == "__main__":
    unittest.main()
