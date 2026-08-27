import tempfile
import unittest
from pathlib import Path
from threading import Event

from backend.jobs import JobManager
from backend.jobs.media import output_path
from backend.settings import AppSettings, DirectorySettings


class FakeCensor:
    instances = []
    block: Event | None = None
    started = Event()
    create_partial_output = False

    def __init__(self, input_file, output_file, *args, **kwargs):
        self.input_file = Path(input_file)
        self.output_file = Path(output_file)
        self.options = kwargs
        self.__class__.instances.append(self)

    def process(self, report_only=False):
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
        if not report_only:
            callback({"event": "progress", "stage": "censoring", "percent": 75.0, "fps": 120.0})
            self.output_file.write_bytes(b"output")
        return True


class JobManagerTests(unittest.TestCase):
    def setUp(self):
        FakeCensor.instances = []
        FakeCensor.block = None
        FakeCensor.started = Event()
        FakeCensor.create_partial_output = False

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


if __name__ == "__main__":
    unittest.main()