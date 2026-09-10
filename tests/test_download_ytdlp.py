import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.runtime.dependencies import YTDLP_RELEASE_URL, YTDLP_VERSION
from scripts.download_ytdlp import main


class DownloadYtdlpTests(unittest.TestCase):
    def test_approved_binary_is_verified_before_replacement(self):
        binary = b"fake-yt-dlp-binary"
        checksum_line = f"{hashlib.sha256(binary).hexdigest()}  yt-dlp.exe\n"

        def fake_urlopen(url, timeout=60):
            if url == YTDLP_RELEASE_URL:
                return io.BytesIO(binary)
            if url.endswith("/SHA2-256SUMS"):
                return io.BytesIO(checksum_line.encode("utf-8"))
            raise AssertionError(f"unexpected URL: {url}")

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            completed = type("Completed", (), {"returncode": 0, "stdout": f"{YTDLP_VERSION}\n", "stderr": ""})()
            with (
                patch("scripts.download_ytdlp.urllib.request.urlopen", side_effect=fake_urlopen),
                patch("scripts.download_ytdlp.subprocess.run", return_value=completed) as run,
            ):
                exit_code = main(["--root", str(root)])

            destination = root / "dependencies" / "yt-dlp" / "yt-dlp.exe"
            self.assertEqual(exit_code, 0)
            self.assertEqual(destination.read_bytes(), binary)
            run.assert_called_once()

    def test_failed_binary_is_not_replaced(self):
        binary = b"corrupt-yt-dlp-binary"
        checksum_line = f"{hashlib.sha256(binary).hexdigest()}  yt-dlp.exe\n"

        def fake_urlopen(url, timeout=60):
            if url == YTDLP_RELEASE_URL:
                return io.BytesIO(binary)
            if url.endswith("/SHA2-256SUMS"):
                return io.BytesIO(checksum_line.encode("utf-8"))
            raise AssertionError(f"unexpected URL: {url}")

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            destination = root / "dependencies" / "yt-dlp" / "yt-dlp.exe"
            destination.parent.mkdir(parents=True)
            destination.write_bytes(b"existing-working-binary")
            failed = type("Completed", (), {"returncode": 1, "stdout": "", "stderr": "PyInstaller archive error"})()
            with (
                patch("scripts.download_ytdlp.urllib.request.urlopen", side_effect=fake_urlopen),
                patch("scripts.download_ytdlp.subprocess.run", return_value=failed),
                self.assertRaisesRegex(RuntimeError, "PyInstaller archive error"),
            ):
                main(["--root", str(root)])

            self.assertEqual(destination.read_bytes(), b"existing-working-binary")
            self.assertEqual(list(destination.parent.glob("*.partial")), [])


if __name__ == "__main__":
    unittest.main()