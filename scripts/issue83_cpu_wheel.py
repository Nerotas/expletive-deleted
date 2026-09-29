"""Make the pinned CTranslate2 Windows wheel CPU-only by omitting cuDNN.

This Phase 1B candidate transformation is not an installer release approval.
It verifies the exact upstream wheel and RECORD, removes one known DLL, and
rewrites RECORD. The source wheel remains untouched.
"""

from __future__ import annotations

import argparse
import base64
import copy
import csv
import hashlib
import io
from pathlib import Path, PurePosixPath
import zipfile


WHEEL_NAME = "ctranslate2-4.8.1-cp313-cp313-win_amd64.whl"
WHEEL_SHA256 = "d52499f05a60a791aeadee28d609efa130142f376d1ea76b2b1c593bb01f8827"
OMITTED_MEMBER = "ctranslate2/cudnn64_9.dll"
OMITTED_SHA256 = "9edbcdff73b0af070eb160b2ce66e59feca04aa017351d8eedcc5e8e149967d2"
RECORD_MEMBER = "ctranslate2-4.8.1.dist-info/RECORD"


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _record_hash(data: bytes) -> str:
    return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")


def _validate_record(wheel: zipfile.ZipFile, record_member: str) -> list[list[str]]:
    files = {item.filename for item in wheel.infolist() if not item.is_dir()}
    rows = list(csv.reader(io.StringIO(wheel.read(record_member).decode("utf-8"))))
    if len(rows) != len(files) or {row[0] for row in rows if len(row) == 3} != files:
        raise ValueError("Wheel RECORD does not enumerate each file exactly once")
    for row in rows:
        if len(row) != 3:
            raise ValueError("Malformed wheel RECORD row")
        name, digest, size = row
        if name == record_member:
            if digest or size:
                raise ValueError("Wheel RECORD must not hash itself")
            continue
        data = wheel.read(name)
        if digest != _record_hash(data) or size != str(len(data)):
            raise ValueError(f"Wheel RECORD mismatch: {name}")
    return rows


def omit_member(
    input_wheel: Path,
    output_wheel: Path,
    *,
    expected_wheel_sha256: str = WHEEL_SHA256,
    omitted_member: str = OMITTED_MEMBER,
    expected_member_sha256: str = OMITTED_SHA256,
    record_member: str = RECORD_MEMBER,
) -> str:
    """Write a new wheel; never mutate the upstream archive or an existing output."""
    if not input_wheel.is_file() or not output_wheel.parent.is_dir():
        raise ValueError("Input wheel and output parent directory must exist")
    if input_wheel.resolve() == output_wheel.resolve() or output_wheel.exists():
        raise FileExistsError("Output must be a new path distinct from the input")
    if _digest(input_wheel.read_bytes()) != expected_wheel_sha256:
        raise ValueError("Upstream wheel SHA-256 mismatch")

    with zipfile.ZipFile(input_wheel) as original:
        infos = original.infolist()
        names = [item.filename for item in infos]
        if len(names) != len(set(names)) or omitted_member not in names or record_member not in names:
            raise ValueError("Wheel has duplicate or missing required members")
        if any(
            name.startswith("/")
            or ".." in PurePosixPath(name).parts
            or "\\" in name
            or ":" in name.split("/", 1)[0]
            for name in names
        ):
            raise ValueError("Wheel has an unsafe member path")
        if _digest(original.read(omitted_member)) != expected_member_sha256:
            raise ValueError("cuDNN member SHA-256 mismatch")
        rows = _validate_record(original, record_member)
        updated_record = io.StringIO(newline="")
        csv.writer(updated_record, lineterminator="\n").writerows(
            row for row in rows if row[0] != omitted_member
        )
        try:
            with output_wheel.open("xb") as destination:
                with zipfile.ZipFile(destination, "w") as transformed:
                    for info in infos:
                        if info.filename == omitted_member:
                            continue
                        data = (
                            updated_record.getvalue().encode("utf-8")
                            if info.filename == record_member
                            else original.read(info.filename)
                        )
                        transformed.writestr(copy.copy(info), data)
        except Exception:
            # Only the new output created by this call may be removed.
            output_wheel.unlink(missing_ok=True)
            raise

    try:
        with zipfile.ZipFile(output_wheel) as result:
            _validate_record(result, record_member)
            if omitted_member in result.namelist():
                raise AssertionError("cuDNN remains in transformed wheel")
    except Exception:
        output_wheel.unlink(missing_ok=True)
        raise
    return _digest(output_wheel.read_bytes())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_wheel", type=Path)
    parser.add_argument("output_wheel", type=Path)
    args = parser.parse_args()
    if args.input_wheel.name != WHEEL_NAME or args.output_wheel.name != WHEEL_NAME:
        parser.error(f"Both archives must be named {WHEEL_NAME}")
    print(omit_member(args.input_wheel, args.output_wheel))


if __name__ == "__main__":
    main()
