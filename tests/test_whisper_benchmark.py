import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from backend.filesystem.locking import StoreBusyError
from scripts.benchmark_whisper import compare_reference, compare_to_standard, experiment_slot, measure, write_json


def cooperative_worker(connection, cancellation, audio, size, repeats):
    for index in range(repeats + 1):
        connection.send({"event": "run_started", "index": index})
        connection.send({
            "event": "run_completed", "index": index, "seconds": float(index + 1),
            "segments": [], "progress": [],
        })
    connection.send({"event": "cancellation_started"})
    while not cancellation.wait(0.01):
        pass
    connection.send({"event": "cancelled"})
    connection.close()


def blocked_worker(connection, cancellation, audio, size, repeats):
    connection.send({"event": "cancellation_started"})
    time.sleep(20)


def failed_worker(connection, cancellation, audio, size, repeats):
    connection.send({"event": "error", "type": "RuntimeError", "detail": "out of memory"})
    connection.close()


class ReferenceAgreementTests(unittest.TestCase):
    def word(self, text="example", start=1.0, end=1.4):
        return {"word": text, "start": start, "end": end}

    def score(self, detected, reference):
        return compare_reference([{"words": detected}], reference, {"example"})

    def test_punctuation_and_case_follow_configured_token_matching(self):
        result = self.score([self.word(' "Example!" ')], [self.word()])
        self.assertEqual(result["recall"], 1)
        self.assertEqual(result["unmatched_detections"], 0)
        self.assertIn("not_manually_verified", result["status"])

    def test_one_detection_cannot_match_two_reference_occurrences(self):
        result = self.score([self.word()], [self.word(), self.word(start=1.5, end=1.8)])
        self.assertEqual(result["missed"], 1)
        self.assertEqual(result["recall"], 0.5)

    def test_silence_reference_does_not_claim_perfect_recall(self):
        result = self.score([self.word()], [])
        self.assertIsNone(result["recall"])
        self.assertEqual(result["unmatched_detections"], 1)

    def test_padding_coverage_is_distinct_from_raw_boundary_error(self):
        result = self.score([self.word(start=1.2, end=1.5)], [self.word()])
        self.assertEqual(result["uncovered_reference_intervals_at_150ms_padding"], 1)
        self.assertAlmostEqual(result["maximum_boundary_error_seconds"], 0.2)

    def test_wrong_temporal_occurrence_is_missed_and_unmatched(self):
        result = self.score([self.word(start=10, end=11)], [self.word()])
        self.assertEqual(result["missed"], 1)
        self.assertEqual(result["unmatched_detections"], 1)

    def test_additional_boundary_error_is_checked_per_occurrence(self):
        baseline = self.score(
            [self.word(start=1.0, end=1.4), self.word(start=3.0, end=3.6)],
            [self.word(), self.word(start=3.0, end=3.4)],
        )
        changed = self.score(
            [self.word(start=1.12, end=1.4), self.word(start=3.0, end=3.4)],
            [self.word(), self.word(start=3.0, end=3.4)],
        )
        # Comparing only maximum errors would incorrectly report an improvement.
        result = compare_to_standard(changed, baseline)
        self.assertAlmostEqual(result["maximum_additional_boundary_error_seconds"], 0.12)
        self.assertFalse(result["timestamp_screen_passed"])

    def test_empty_reference_never_passes_timestamp_screen(self):
        score = self.score([], [])
        self.assertFalse(compare_to_standard(score, score)["timestamp_screen_passed"])

    def test_atomic_json_leaves_no_pending_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "summary.json"
            write_json(path, {"complete": True})
            self.assertEqual(list(path.parent.iterdir()), [path])
            self.assertIn('"complete": true', path.read_text())

    def test_busy_desktop_profile_has_actionable_error(self):
        ownership = MagicMock()
        ownership.__enter__.side_effect = StoreBusyError("busy")
        with patch("scripts.benchmark_whisper.SettingsStore") as store:
            store.return_value.desktop_owner.return_value = ownership
            with self.assertRaisesRegex(RuntimeError, "Close the desktop app"):
                with experiment_slot():
                    self.fail("A busy profile must not start a benchmark")

    def test_profile_ownership_is_released_on_failure(self):
        ownership = MagicMock()
        ownership.__exit__.return_value = False
        with patch("scripts.benchmark_whisper.SettingsStore") as store:
            store.return_value.desktop_owner.return_value = ownership
            with self.assertRaisesRegex(ValueError, "failed"):
                with experiment_slot():
                    raise ValueError("failed")
        ownership.__exit__.assert_called_once()


@unittest.skipUnless(os.name == "nt", "Windows native memory sampling")
class WorkerLifecycleTests(unittest.TestCase):
    def run_worker(self, worker, timeout=10):
        with tempfile.TemporaryDirectory() as temporary, patch(
            "scripts.benchmark_whisper._worker", worker,
        ):
            return measure(Path("unused.wav"), 1, 3, timeout, Path(temporary))

    def test_initial_run_is_excluded_and_cooperative_cancel_finishes(self):
        result = self.run_worker(cooperative_worker)
        self.assertEqual(result["warm_median_seconds"], 3.0)
        self.assertEqual(len(result["runs"]), 4)
        self.assertTrue(result["warm_runs_complete"])
        self.assertTrue(result["cancellation"]["threshold_passed"])
        self.assertEqual(result["exitcode"], 0)

    def test_blocked_worker_is_terminated_and_next_worker_recovers(self):
        result = self.run_worker(blocked_worker)
        self.assertTrue(result["cancellation"]["forced_termination"])
        self.assertFalse(result["cancellation"]["threshold_passed"])
        recovered = self.run_worker(cooperative_worker)
        self.assertTrue(recovered["warm_runs_complete"])

    def test_memory_error_is_reported_without_retry_or_success_median(self):
        result = self.run_worker(failed_worker)
        self.assertEqual(result["errors"][0]["detail"], "out of memory")
        self.assertFalse(result["warm_runs_complete"])
        self.assertIsNone(result["warm_median_seconds"])

    def test_timeout_preserves_failure_diagnostics(self):
        with tempfile.TemporaryDirectory() as temporary, patch(
            "scripts.benchmark_whisper._worker", blocked_worker,
        ):
            output = Path(temporary)
            with self.assertRaisesRegex(TimeoutError, "exceeded"):
                measure(Path("unused.wav"), 1, 3, 0.5, output)
            self.assertTrue((output / "batch-1-failure.json").is_file())


if __name__ == "__main__":
    unittest.main()
