import unittest
from pathlib import Path

from backend.jobs import JobError, JobEvent, JobRecord, JobSubmissionResult


class JobModelTests(unittest.TestCase):
    def test_job_and_progress_event_are_json_ready(self):
        source = Path("C:/media/movie.mkv").resolve()
        job = JobRecord("job-1", source, "censor", "transcribing", 42.5)
        event = JobEvent(
            "progress",
            job.id,
            stage=job.status,
            percent=job.progress_percent,
            eta_seconds=12.0,
        )

        self.assertEqual(job.to_dict()["source"], str(source))
        self.assertEqual(event.to_dict()["percent"], 42.5)

    def test_failed_job_requires_structured_error(self):
        source = Path("C:/media/movie.mkv").resolve()

        with self.assertRaisesRegex(ValueError, "require an error"):
            JobRecord("job-1", source, "censor", "failed")

        error = JobError("ffmpeg_failed", "Censoring failed", "exit code 1", True)
        job = JobRecord("job-1", source, "censor", "failed", error=error)
        event = JobEvent("error", job.id, stage=job.status, error=error)

        self.assertEqual(event.to_dict()["error"]["code"], "ffmpeg_failed")

    def test_invalid_progress_is_rejected(self):
        source = Path("C:/media/movie.mkv").resolve()

        with self.assertRaisesRegex(ValueError, "0 through 100"):
            JobRecord("job-1", source, "censor", progress_percent=101)

    def test_submission_results_are_discriminated_and_json_ready(self):
        source = Path("C:/media/movie.mkv").resolve()
        job = JobRecord("job-1", source, "report_only")

        queued = JobSubmissionResult(source, "queued", job=job).to_dict()
        rejected = JobSubmissionResult(
            source,
            "rejected",
            code="already_queued",
            detail="Already waiting",
        ).to_dict()

        self.assertEqual(queued["job"]["id"], "job-1")
        self.assertNotIn("code", queued)
        self.assertEqual(rejected["code"], "already_queued")
        self.assertNotIn("job", rejected)

    def test_reprocessing_flags_are_mode_specific_and_serialized(self):
        source = Path("C:/media/movie.mkv").resolve()
        retranscribe = JobRecord(
            "job-1",
            source,
            "report_only",
            force_transcribe=True,
        )
        retranscode = JobRecord(
            "job-2",
            source,
            "censor",
            overwrite_output=True,
        )

        self.assertTrue(retranscribe.to_dict()["force_transcribe"])
        self.assertTrue(retranscode.to_dict()["overwrite_output"])
        with self.assertRaisesRegex(ValueError, "report-only"):
            JobRecord("job-3", source, "censor", force_transcribe=True)
        with self.assertRaisesRegex(ValueError, "censor jobs"):
            JobRecord("job-4", source, "report_only", overwrite_output=True)


if __name__ == "__main__":
    unittest.main()
