import tempfile
import unittest
from pathlib import Path

from scripts.probe_issue83_runtime import probe


class Issue83RuntimeProbeTests(unittest.TestCase):
    def test_rejects_missing_media_without_importing_candidate_packages(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            site_packages = root / "site-packages"
            site_packages.mkdir()
            with self.assertRaisesRegex(ValueError, "Existing site-packages, video, and audio"):
                probe(site_packages, root / "missing.mp4", root / "missing.wav", None, False)

    def test_no_cudnn_mode_fails_before_native_import(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            site_packages = root / "site-packages"
            library = site_packages / "ctranslate2" / "cudnn64_9.dll"
            library.parent.mkdir(parents=True)
            library.write_bytes(b"synthetic")
            video = root / "sample.mp4"
            audio = root / "sample.wav"
            video.write_bytes(b"synthetic")
            audio.write_bytes(b"synthetic")
            with self.assertRaisesRegex(ValueError, "cuDNN DLL remains"):
                probe(site_packages, video, audio, None, True)


if __name__ == "__main__":
    unittest.main()
