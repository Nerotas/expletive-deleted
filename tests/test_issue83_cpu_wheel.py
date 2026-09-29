"""Regression checks for the Phase 1B cuDNN omission candidate."""

from __future__ import annotations

import csv
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.issue83_cpu_wheel import _record_hash, omit_member


class OmitCuDNNTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.input = self.root / "input.whl"
        self.record = "demo-1.0.dist-info/RECORD"
        self.cudnn = "demo/cudnn64_9.dll"
        self.data = {"demo/__init__.py": b"version = 1\n", self.cudnn: b"synthetic DLL"}
        self._write_input()

    def _write_input(self, *, bad_record: bool = False, omit_cudnn: bool = False) -> None:
        files = {name: data for name, data in self.data.items() if not (omit_cudnn and name == self.cudnn)}
        record = io.StringIO(newline="")
        writer = csv.writer(record, lineterminator="\n")
        for name, data in files.items():
            writer.writerow([name, "sha256=wrong" if bad_record else _record_hash(data), len(data)])
        writer.writerow([self.record, "", ""])
        with zipfile.ZipFile(self.input, "w", compression=zipfile.ZIP_DEFLATED) as wheel:
            for name, data in files.items():
                wheel.writestr(name, data)
            wheel.writestr(self.record, record.getvalue())

    def _transform(self, output: Path) -> str:
        return omit_member(
            self.input,
            output,
            expected_wheel_sha256=hashlib.sha256(self.input.read_bytes()).hexdigest(),
            omitted_member=self.cudnn,
            expected_member_sha256=hashlib.sha256(self.data[self.cudnn]).hexdigest(),
            record_member=self.record,
        )

    def test_removes_only_cudnn_and_is_deterministic(self) -> None:
        original_hash = hashlib.sha256(self.input.read_bytes()).hexdigest()
        first, second = self.root / "first.whl", self.root / "second.whl"
        self.assertEqual(self._transform(first), self._transform(second))
        with zipfile.ZipFile(first) as wheel:
            self.assertEqual(set(wheel.namelist()), {"demo/__init__.py", self.record})
            self.assertEqual(wheel.read("demo/__init__.py"), self.data["demo/__init__.py"])
        self.assertEqual(hashlib.sha256(self.input.read_bytes()).hexdigest(), original_hash)

    def test_fails_closed_on_input_hash_mismatch(self) -> None:
        with self.assertRaisesRegex(ValueError, "Upstream wheel"):
            omit_member(self.input, self.root / "output.whl")
        self.assertFalse((self.root / "output.whl").exists())

    def test_fails_closed_on_record_mismatch(self) -> None:
        self._write_input(bad_record=True)
        with self.assertRaisesRegex(ValueError, "RECORD mismatch"):
            self._transform(self.root / "output.whl")

    def test_fails_closed_on_missing_member(self) -> None:
        self._write_input(omit_cudnn=True)
        with self.assertRaisesRegex(ValueError, "missing required"):
            self._transform(self.root / "output.whl")

    def test_refuses_existing_output(self) -> None:
        output = self.root / "output.whl"
        output.write_bytes(b"leave untouched")
        with self.assertRaises(FileExistsError):
            self._transform(output)
        self.assertEqual(output.read_bytes(), b"leave untouched")


if __name__ == "__main__":
    unittest.main()
