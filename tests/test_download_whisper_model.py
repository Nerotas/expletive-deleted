import unittest
from unittest.mock import patch

from backend.runtime import WHISPER_MODEL_ID, WHISPER_MODEL_REVISION
from scripts.download_whisper_model import main


class DownloadWhisperModelTests(unittest.TestCase):
    def test_worker_downloads_only_the_pinned_model_revision(self):
        with patch("faster_whisper.utils.download_model", return_value="model-path") as download:
            exit_code = main(["--cache-dir", "cache"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(download.call_args.args[0], WHISPER_MODEL_ID)
        self.assertEqual(download.call_args.kwargs["revision"], WHISPER_MODEL_REVISION)


if __name__ == "__main__":
    unittest.main()