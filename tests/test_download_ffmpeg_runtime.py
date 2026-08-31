import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts.download_ffmpeg_runtime import main


class DownloadFfmpegRuntimeTests(unittest.TestCase):
    def test_approved_runtime_is_copied_under_the_per_user_component_directory(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            fetched = root / "provider-cache"
            fetched.mkdir()
            ffmpeg = fetched / "ffmpeg.exe"
            ffprobe = fetched / "ffprobe.exe"
            ffmpeg.write_bytes(b"ffmpeg")
            ffprobe.write_bytes(b"ffprobe")
            fake_module = SimpleNamespace(
                run=SimpleNamespace(
                    get_or_fetch_platform_executables_else_raise=lambda: (
                        str(ffmpeg),
                        str(ffprobe),
                    )
                )
            )

            with patch.dict(sys.modules, {"static_ffmpeg": fake_module}):
                exit_code = main(["--root", str(root)])

            installed = root / "dependencies" / "ffmpeg" / "bin"
            manifest = json.loads((root / "ffmpeg-runtime.json").read_text(encoding="utf-8"))
            self.assertEqual(exit_code, 0)
            self.assertEqual((installed / "ffmpeg.exe").read_bytes(), b"ffmpeg")
            self.assertEqual((installed / "ffprobe.exe").read_bytes(), b"ffprobe")
            self.assertEqual(Path(manifest["ffmpeg"]), (installed / "ffmpeg.exe").resolve())
            self.assertEqual(Path(manifest["ffprobe"]), (installed / "ffprobe.exe").resolve())
            self.assertEqual(list(installed.glob("*.partial")), [])


if __name__ == "__main__":
    unittest.main()
