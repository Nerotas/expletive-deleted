import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.inspect_installed_dependencies import _target_environment
from scripts.inspect_issue83_wheels import _inspect_archive


class Issue83WheelInspectionTests(unittest.TestCase):
    def test_notice_inventory_excludes_directories_and_reads_target_dependencies(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            archive = Path(temporary_directory) / "sample-1.0-py3-none-any.whl"
            with zipfile.ZipFile(archive, "w") as wheel:
                wheel.writestr("sample-1.0.dist-info/METADATA", "\n".join((
                    "Metadata-Version: 2.3",
                    "Name: sample",
                    "Version: 1.0",
                    "License-Expression: MIT",
                    'Requires-Dist: win-only>=1; sys_platform == "win32"',
                    'Requires-Dist: linux-only>=1; sys_platform == "linux"',
                    "",
                )))
                wheel.writestr("sample-1.0.dist-info/licenses/", "")
                wheel.writestr("sample-1.0.dist-info/licenses/LICENSE.txt", "license text")
                wheel.writestr("sample/native.pyd", b"native")

            result = _inspect_archive(archive, _target_environment("3.13"))

            self.assertEqual(result["license_metadata"], "MIT")
            self.assertEqual(result["dependencies"], ["win-only>=1; sys_platform == \"win32\""])
            self.assertEqual(result["native_files"], ["sample/native.pyd"])
            self.assertEqual(result["notice_files"], ["sample-1.0.dist-info/licenses/LICENSE.txt"])


if __name__ == "__main__":
    unittest.main()
