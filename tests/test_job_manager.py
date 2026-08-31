import tempfile
import unittest
import json
from pathlib import Path
from threading import Event

from backend.jobs import JobManager, JobSubmissionError
from backend.jobs.media import output_path
from backend.settings import AppSettings, DirectorySettings


class FakeCensor:
    instances = []
    processed_sources = []
    block: Event | None = None
    started = Event()
    create_partial_output = False
    fail_processing = False
    process_options = []

    def __init__(self, input_file, output_file, *args, **kwargs):
        self.input_file = Path(input_file)
        self.output_file = Path(output_file)
        self.transcripts_dir = Path(args[1])
        self.options = kwargs
        self.__class__.instances.append(self)

    def process(self, report_only=False, force_transcribe=False):
        self.__class__.process_options.append({
            "report_only": report_only,
            "force_transcribe": force_transcribe,
        })
        self.__class__.processed_sources.append(self.input_file.name)
        self.__class__.started.set()
        callback = self.options["progress_callback"]
        callback({"event": "progress", "stage": "transcribing", "percent": 50.0, "eta_seconds": 1.0})
        callback({"event": "detection", "word": "example", "start": 1.0, "end": 1.5})
        if self.create_partial_output:
            self.output_file.write_bytes(b"partial")
        if self.block is not None:
            self.block.wait(timeout=2)
        if self.options["cancellation"].is_set():
            return False
        self.transcripts_dir.mkdir(parents=True, exist_ok=True)
        (self.transcripts_dir / f"{self.input_file.stem}-transcript.json").write_text(
            json.dumps(
                {
                    "text": "example",
                    "words": [{"word": "example", "start": 1.0, "end": 1.5}],
                    "audio_source": "full_mix",
                    "whisper_library": "faster-whisper",
                    "whisper_model": "large",
                }
            ),
            encoding="utf-8",
        )
        if not report_only:
            callback({"event": "progress", "stage": "censoring", "percent": 75.0, "fps": 120.0})
            self.output_file.write_bytes(b"output")
        return not self.fail_processing


class JobManagerTests(unittest.TestCase):
    def setUp(self):
        FakeCensor.instances = []
        FakeCensor.processed_sources = []
        FakeCensor.block = None
        FakeCensor.started = Event()
        FakeCensor.create_partial_output = False
        FakeCensor.fail_processing = False
        FakeCensor.process_options = []

    def create_settings(self, root: Path) -> AppSettings:
        directories = DirectorySettings(
            input=root / "Ready",
            output=root / "Finished",
            archive=root / "Processed",
            transcripts=root / "Transcripts",
        )
        for directory in (
            directories.input,
            directories.output,
            directories.archive,
            directories.transcripts,
        ):
            directory.mkdir()
        return AppSettings(directories=directories)

    def test_censor_job_emits_progress_and_verifies_output(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings = self.create_settings(Path(temporary_directory))
            source = settings.directories.input / "movie.mkv"
            source.write_bytes(b"source")
            manager = JobManager(settings, censor_factory=FakeCensor)
            try:
                job = manager.submit(source, "censor")
                completed = manager.wait(job.id, timeout=2)
                events = manager.events(job.id)
            finally:
                manager.close()

        self.assertEqual(completed.status, "completed")
        self.assertTrue(any(event.event == "progress" and event.fps == 120.0 for event in events))
        self.assertTrue(any(event.event == "detection" and event.word == "example" for event in events))
        self.assertEqual([event.sequence for event in events], sorted(event.sequence for event in events))

    def test_report_only_stops_at_transcribed_without_output(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings = self.create_settings(Path(temporary_directory))
            source = settings.directories.input / "movie.mkv"
            source.write_bytes(b"source")
            manager = JobManager(settings, censor_factory=FakeCensor)
            try:
                job = manager.submit(source, "report_only")
                completed = manager.wait(job.id, timeout=2)
            finally:
                manager.close()

        self.assertEqual(completed.status, "transcribed")
        self.assertFalse(output_path(source, settings.directories.output).exists())

    def test_queued_job_can_be_cancelled_without_running(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings = self.create_settings(Path(temporary_directory))
            first = settings.directories.input / "first.mkv"
            second = settings.directories.input / "second.mkv"
            first.write_bytes(b"source")
            second.write_bytes(b"source")
            blocker = Event()
            FakeCensor.block = blocker
            manager = JobManager(settings, censor_factory=FakeCensor)
            try:
                first_job = manager.submit(first)
                second_job = manager.submit(second)
                cancelled = manager.cancel(second_job.id)
                blocker.set()
                manager.wait(first_job.id, timeout=2)
                final = manager.wait(second_job.id, timeout=2)
            finally:
                manager.close()

        self.assertEqual(cancelled.status, "cancelled")
        self.assertEqual(final.status, "cancelled")
        self.assertEqual(len(FakeCensor.instances), 1)

    def test_active_cancellation_removes_partial_output_and_retains_source(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings = self.create_settings(Path(temporary_directory))
            source = settings.directories.input / "movie.mkv"
            source.write_bytes(b"source")
            blocker = Event()
            FakeCensor.block = blocker
            FakeCensor.create_partial_output = True
            manager = JobManager(settings, censor_factory=FakeCensor)
            try:
                job = manager.submit(source)
                self.assertTrue(FakeCensor.started.wait(timeout=1))
                manager.cancel(job.id)
                blocker.set()
                final = manager.wait(job.id, timeout=2)
                source_exists = source.exists()
                output_exists = output_path(source, settings.directories.output).exists()
            finally:
                manager.close()

        self.assertEqual(final.status, "cancelled")
        self.assertTrue(source_exists)
        self.assertFalse(output_exists)

    def test_jobs_run_sequentially_in_submission_order(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings = self.create_settings(Path(temporary_directory))
            sources = [settings.directories.input / name for name in ("one.mkv", "two.mkv", "three.mkv")]
            for source in sources:
                source.write_bytes(b"source")
            blocker = Event()
            FakeCensor.block = blocker
            manager = JobManager(settings, censor_factory=FakeCensor)
            try:
                jobs = [manager.submit(source, "report_only") for source in sources]
                self.assertTrue(FakeCensor.started.wait(timeout=1))
                self.assertEqual(len(FakeCensor.instances), 1)
                blocker.set()
                completed = [manager.wait(job.id, timeout=2) for job in jobs]
            finally:
                manager.close()

        self.assertEqual([job.status for job in completed], ["transcribed"] * 3)
        self.assertEqual(FakeCensor.processed_sources, [source.name for source in sources])

    def test_duplicate_non_terminal_job_is_rejected_but_cancelled_job_can_retry(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings = self.create_settings(Path(temporary_directory))
            source = settings.directories.input / "movie.mkv"
            source.write_bytes(b"source")
            blocker = Event()
            FakeCensor.block = blocker
            manager = JobManager(settings, censor_factory=FakeCensor)
            try:
                first = manager.submit(source, "report_only")
                self.assertTrue(FakeCensor.started.wait(timeout=1))
                with self.assertRaises(JobSubmissionError) as rejection:
                    manager.submit(source, "report_only")
                manager.cancel(first.id)
                blocker.set()
                manager.wait(first.id, timeout=2)
                retry = manager.submit(source, "report_only")
                completed = manager.wait(retry.id, timeout=2)
            finally:
                manager.close()

        self.assertEqual(rejection.exception.code, "already_queued")
        self.assertEqual(completed.status, "transcribed")

    def test_submit_many_queues_valid_sources_and_preserves_ordered_rejections(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings = self.create_settings(Path(temporary_directory))
            first = settings.directories.input / "first.mkv"
            missing = settings.directories.input / "missing.mkv"
            second = settings.directories.input / "second.mkv"
            first.write_bytes(b"source")
            second.write_bytes(b"source")
            manager = JobManager(settings, censor_factory=FakeCensor)
            try:
                results = manager.submit_many([first, missing, second], "report_only")
                queued_jobs = [result.job for result in results if result.job]
                completed = [manager.wait(job.id, timeout=2) for job in queued_jobs]
            finally:
                manager.close()

        self.assertEqual([result.status for result in results], ["queued", "rejected", "queued"])
        self.assertEqual(results[1].code, "unavailable")
        self.assertEqual([job.source.name for job in completed], ["first.mkv", "second.mkv"])

    def test_submission_rejection_codes_cover_path_type_and_output_conflicts(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            settings = self.create_settings(root)
            outside = root / "outside.mkv"
            outside.write_bytes(b"source")
            unsupported = settings.directories.input / "notes.txt"
            unsupported.write_text("notes", encoding="utf-8")
            source = settings.directories.input / "movie.mkv"
            source.write_bytes(b"source")
            existing_output = output_path(
                source,
                settings.directories.output,
                settings.directories.input,
            )
            existing_output.write_bytes(b"existing")
            manager = JobManager(settings, censor_factory=FakeCensor)
            try:
                with self.assertRaises(JobSubmissionError) as outside_error:
                    manager.submit(outside, "report_only")
                with self.assertRaises(JobSubmissionError) as unsupported_error:
                    manager.submit(unsupported, "report_only")
                with self.assertRaises(JobSubmissionError) as output_error:
                    manager.submit(source, "censor")
            finally:
                manager.close()

        self.assertEqual(outside_error.exception.code, "outside_input")
        self.assertEqual(unsupported_error.exception.code, "unsupported")
        self.assertEqual(output_error.exception.code, "existing_output")

    def test_finished_file_can_force_a_fresh_transcript_without_touching_output(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings = self.create_settings(Path(temporary_directory))
            source = settings.directories.input / "movie.mkv"
            source.write_bytes(b"source")
            transcript = settings.directories.transcripts / "movie-transcript.json"
            transcript.write_text('{"text":"old"}', encoding="utf-8")
            existing_output = output_path(
                source,
                settings.directories.output,
                settings.directories.input,
            )
            existing_output.write_bytes(b"existing output")
            manager = JobManager(settings, censor_factory=FakeCensor)
            try:
                job = manager.submit(source, "report_only", force_transcribe=True)
                completed = manager.wait(job.id, timeout=2)
            finally:
                manager.close()
            output_bytes = existing_output.read_bytes()

        self.assertEqual(completed.status, "transcribed")
        self.assertTrue(completed.force_transcribe)
        self.assertTrue(FakeCensor.process_options[0]["force_transcribe"])
        self.assertEqual(output_bytes, b"existing output")

    def test_finished_file_retranscode_replaces_output_after_success(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings = self.create_settings(Path(temporary_directory))
            source = settings.directories.input / "movie.mkv"
            source.write_bytes(b"source")
            existing_output = output_path(
                source,
                settings.directories.output,
                settings.directories.input,
            )
            existing_output.write_bytes(b"existing output")
            manager = JobManager(settings, censor_factory=FakeCensor)
            try:
                job = manager.submit(source, "censor", overwrite_output=True)
                completed = manager.wait(job.id, timeout=2)
            finally:
                manager.close()
            output_bytes = existing_output.read_bytes()

        self.assertEqual(completed.status, "completed")
        self.assertTrue(completed.overwrite_output)
        self.assertFalse(FakeCensor.process_options[0]["force_transcribe"])
        self.assertEqual(output_bytes, b"output")

    def test_failed_retranscode_preserves_previous_verified_output(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings = self.create_settings(Path(temporary_directory))
            source = settings.directories.input / "movie.mkv"
            source.write_bytes(b"source")
            existing_output = output_path(
                source,
                settings.directories.output,
                settings.directories.input,
            )
            existing_output.write_bytes(b"existing output")
            FakeCensor.fail_processing = True
            manager = JobManager(settings, censor_factory=FakeCensor)
            try:
                job = manager.submit(source, "censor", overwrite_output=True)
                completed = manager.wait(job.id, timeout=2)
            finally:
                manager.close()

            output_bytes = existing_output.read_bytes()
            partials = list(existing_output.parent.glob("*.partial*"))

        self.assertEqual(completed.status, "failed")
        self.assertEqual(output_bytes, b"existing output")
        self.assertEqual(partials, [])


if __name__ == "__main__":
    unittest.main()
