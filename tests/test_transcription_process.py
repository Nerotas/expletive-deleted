import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from threading import Event, Thread
from unittest.mock import patch

from backend.runtime.transcription_process import transcribe_in_process


class TranscriptionProcessTests(unittest.TestCase):
    def invoke(self, cancellation):
        def check():
            if cancellation.is_set():
                raise InterruptedError("Cancelled")
        return transcribe_in_process(
            "faster-whisper", "large-v3", "cpu", Path("."), "clip.wav",
            4, cancellation, check,
        )

    def test_streams_normalized_segments_and_completes(self):
        bootstrap = (
            "import json,sys; json.load(sys.stdin); "
            "print(json.dumps({'type':'ready'}),flush=True); "
            "print(json.dumps({'type':'segment','segment':{'text':' Hi',"
            "'start':1.0,'end':2.0,'words':[{'word':' Hi','start':1.1,'end':1.9}]}}),flush=True); "
            "print(json.dumps({'type':'completed'}),flush=True)"
        )
        with patch("backend.runtime.transcription_process._BOOTSTRAP", bootstrap):
            output = list(self.invoke(Event()))
        self.assertEqual(output[0]["words"][0]["end"], 1.9)

    def test_worker_is_the_process_that_executes_python(self):
        bootstrap = (
            "import json,os,sys; json.load(sys.stdin); "
            "print(json.dumps({'type':'ready'}),flush=True); "
            "print(json.dumps({'type':'segment','segment':{'text':str(os.getpid()),"
            "'start':0,'end':1,'words':[]}}),flush=True); "
            "print(json.dumps({'type':'completed'}),flush=True)"
        )
        original_popen = subprocess.Popen
        processes = []
        def capture(*args, **kwargs):
            process = original_popen(*args, **kwargs)
            processes.append(process)
            return process
        with patch("backend.runtime.transcription_process._BOOTSTRAP", bootstrap), patch(
            "backend.runtime.transcription_process.subprocess.Popen", side_effect=capture,
        ):
            output = list(self.invoke(Event()))
        self.assertEqual(len(processes), 1)
        self.assertEqual(int(output[0]["text"]), processes[0].pid)

    def test_running_worker_is_terminated_when_cancelled_and_next_worker_succeeds(self):
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "ready"
            bootstrap = (
                "import json,sys,time,pathlib; json.load(sys.stdin); "
                f"pathlib.Path({str(marker)!r}).touch(); "
                "print(json.dumps({'type':'ready'}),flush=True); time.sleep(60)"
            )
            cancellation = Event()
            started = Event()
            result = []

            def execute():
                started.set()
                try:
                    list(self.invoke(cancellation))
                except Exception as exc:
                    result.append(exc)

            with patch("backend.runtime.transcription_process._BOOTSTRAP", bootstrap), patch(
                "backend.runtime.transcription_process.subprocess.Popen", wraps=subprocess.Popen,
            ) as popen:
                thread = Thread(target=execute)
                thread.start()
                self.assertTrue(started.wait(2))
                deadline = time.monotonic() + 10
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                if not marker.exists():
                    cancellation.set()
                    thread.join(5)
                    self.fail("Worker did not enter the blocking inference stand-in")
                start = time.monotonic()
                cancellation.set()
                thread.join(5)
                elapsed = time.monotonic() - start
                self.assertFalse(thread.is_alive())
                self.assertLess(elapsed, 2.0)
                self.assertEqual(len(result), 1)
                self.assertIsInstance(result[0], InterruptedError)
                self.assertEqual(popen.call_count, 1)
            self.test_streams_normalized_segments_and_completes()

    def test_precancelled_does_not_launch(self):
        cancellation = Event()
        cancellation.set()
        with patch("backend.runtime.transcription_process.subprocess.Popen") as popen:
            with self.assertRaises(InterruptedError):
                list(self.invoke(cancellation))
        popen.assert_not_called()

    def test_worker_failure_is_actionable_without_retry(self):
        bootstrap = (
            "import json,sys; json.load(sys.stdin); "
            "print(json.dumps({'type':'error','detail':'out of memory'}),flush=True)"
        )
        with patch("backend.runtime.transcription_process._BOOTSTRAP", bootstrap), patch(
            "backend.runtime.transcription_process.subprocess.Popen", wraps=subprocess.Popen,
        ) as popen:
            with self.assertRaisesRegex(RuntimeError, "out of memory"):
                list(self.invoke(Event()))
        self.assertEqual(popen.call_count, 1)

    def test_crash_and_missing_completion_are_failures(self):
        for bootstrap in (
            "import os; os._exit(17)",
            "import json,sys; json.load(sys.stdin); print(json.dumps({'type':'ready'}),flush=True)",
        ):
            with self.subTest(bootstrap=bootstrap), patch(
                "backend.runtime.transcription_process._BOOTSTRAP", bootstrap,
            ), self.assertRaisesRegex(RuntimeError, "stopped unexpectedly"):
                list(self.invoke(Event()))

    def test_bad_segment_is_rejected(self):
        bootstrap = (
            "import json,sys; json.load(sys.stdin); print(json.dumps({'type':'ready'}),flush=True); "
            "print(json.dumps({'type':'segment','segment':{'text':'x','start':0,'end':1,"
            "'words':[{'word':'x','start':True,'end':1}]}}),flush=True)"
        )
        with patch("backend.runtime.transcription_process._BOOTSTRAP", bootstrap):
            with self.assertRaisesRegex(RuntimeError, "invalid word"):
                list(self.invoke(Event()))

    def test_callback_failure_terminates_worker(self):
        bootstrap = (
            "import json,sys,time; json.load(sys.stdin); "
            "print(json.dumps({'type':'ready'}),flush=True); time.sleep(60)"
        )
        def fail():
            raise RuntimeError("progress callback failed")

        processes = []
        original_popen = subprocess.Popen
        def capture(*args, **kwargs):
            process = original_popen(*args, **kwargs)
            processes.append(process)
            return process

        with patch("backend.runtime.transcription_process._BOOTSTRAP", bootstrap), patch(
            "backend.runtime.transcription_process.subprocess.Popen", side_effect=capture,
        ):
            with self.assertRaisesRegex(RuntimeError, "progress callback failed"):
                list(transcribe_in_process(
                    "faster-whisper", "large-v3", "cpu", Path("."), "clip.wav",
                    4, Event(), lambda: None, on_ready=fail,
                ))
            self.assertEqual(len(processes), 1)
            self.assertIsNotNone(processes[0].poll())


if __name__ == "__main__":
    unittest.main()
