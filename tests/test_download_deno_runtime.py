import hashlib
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from backend.runtime.dependencies import DENO_CHECKSUM_URL, DENO_RELEASE_URL
from scripts.download_deno_runtime import main


def _build_zip(entry_bytes: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("deno.exe", entry_bytes)
    return buffer.getvalue()


class DownloadDenoRuntimeTests(unittest.TestCase):
    def test_approved_runtime_is_verified_and_extracted_under_the_per_user_component_directory(self):
        entry_bytes = b"fake-deno-binary"
        zip_bytes = _build_zip(entry_bytes)
        checksum_line = f"{hashlib.sha256(zip_bytes).hexdigest()}  deno-x86_64-pc-windows-msvc.zip\n"

        def fake_urlopen(url, timeout=60):
            if url == DENO_RELEASE_URL:
                return io.BytesIO(zip_bytes)
            if url == DENO_CHECKSUM_URL:
                return io.BytesIO(checksum_line.encode("utf-8"))
            raise AssertionError(f"unexpected URL: {url}")

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            with patch("scripts.download_deno_runtime.urllib.request.urlopen", side_effect=fake_urlopen):
                exit_code = main(["--root", str(root)])

            destination = root / "dependencies" / "deno" / "deno.exe"
            self.assertEqual(exit_code, 0)
            self.assertEqual(destination.read_bytes(), entry_bytes)
            self.assertEqual(list(destination.parent.glob("*.partial")), [])
            self.assertEqual(list(destination.parent.glob("*.zip.partial")), [])

    def test_checksum_mismatch_is_rejected_and_leaves_no_partial_files(self):
        zip_bytes = _build_zip(b"fake-deno-binary")
        wrong_checksum = f"{'0' * 64}  deno-x86_64-pc-windows-msvc.zip\n"

        def fake_urlopen(url, timeout=60):
            if url == DENO_RELEASE_URL:
                return io.BytesIO(zip_bytes)
            if url == DENO_CHECKSUM_URL:
                return io.BytesIO(wrong_checksum.encode("utf-8"))
            raise AssertionError(f"unexpected URL: {url}")

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            with (
                patch("scripts.download_deno_runtime.urllib.request.urlopen", side_effect=fake_urlopen),
                self.assertRaisesRegex(RuntimeError, "checksum did not match"),
            ):
                main(["--root", str(root)])

            destination_dir = root / "dependencies" / "deno"
            self.assertFalse((destination_dir / "deno.exe").exists())
            self.assertEqual(list(destination_dir.glob("*")), [])


if __name__ == "__main__":
    unittest.main()
