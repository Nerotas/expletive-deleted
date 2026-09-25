"""Full-content identity and provenance, with no hashing during library polling."""

from __future__ import annotations

import hashlib
import json
import re
from contextlib import contextmanager
from pathlib import Path
from threading import Event
from typing import Callable, BinaryIO

from backend.filesystem.operations import locked_file
from backend.filesystem.paths import RootBinding
from backend.filesystem.publication import Publication


class MediaIdentityError(RuntimeError):
    code = "media_identity_unverified"


def hash_stream(stream: BinaryIO, *, cancellation: Event | None = None,
                progress: Callable[[int], None] | None = None) -> str:
    """Read every byte in bounded chunks, checking cancellation between reads."""
    digest = hashlib.sha256()
    consumed = 0
    while True:
        if cancellation is not None and cancellation.is_set():
            raise InterruptedError("File verification cancelled")
        chunk = stream.read(1024 * 1024)
        if not chunk:
            return digest.hexdigest()
        digest.update(chunk)
        consumed += len(chunk)
        if progress:
            progress(consumed)


@contextmanager
def verified_source(path: Path, *, cancellation=None, progress=None):
    """Keep the Windows read lease until all processing using this digest ends."""
    path = path.absolute()
    with locked_file(RootBinding.capture(path.parent), path):
        size = path.stat().st_size
        with path.open("rb") as stream:
            digest = hash_stream(stream, cancellation=cancellation,
                                 progress=(lambda count: progress(count, size)) if progress else None)
        # Keep the lease after hashing so processing cannot read a replaced source on Windows.
        yield {"algorithm": "sha256", "digest": digest, "size_bytes": size}


def valid_identity(value: object) -> bool:
    return (isinstance(value, dict) and value.get("algorithm") == "sha256"
            and isinstance(value.get("digest"), str)
            and re.fullmatch(r"[0-9a-f]{64}", value["digest"]) is not None
            and type(value.get("size_bytes")) is int and value["size_bytes"] >= 0)


def require_identity(record: dict, expected: dict) -> None:
    actual = record.get("source_identity")
    if not valid_identity(actual):
        raise MediaIdentityError("This artifact has no verified source fingerprint. Existing files are preserved. "
                                 "Choose Retranscribe to create a fresh transcript, or keep the files for manual mapping.")
    if actual != expected:
        raise MediaIdentityError("The source contents do not match this artifact. Existing files are preserved. "
                                 "Choose Retranscribe only if you want a fresh transcript for this source.")


def read_record(path: Path) -> dict:
    with locked_file(RootBinding.capture(path.parent), path):
        value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise MediaIdentityError("Artifact metadata must be a JSON object")
    return value


def provenance_path(output: Path) -> Path:
    return output.with_name(output.name + ".provenance.json")


def valid_provenance(record: dict) -> bool:
    return (record.get("schema_version") == 1 and valid_identity(record.get("source_identity"))
            and isinstance(record.get("processing"), dict)
            and all(isinstance(record.get(key), str) and re.fullmatch(r"[0-9a-f]{64}", record[key])
                    for key in ("transcript_sha256", "output_sha256")))


def publish_output(publication: Publication, censor) -> None:
    """Publish media first; incomplete provenance never authorizes reuse or archival."""
    record = censor.output_provenance
    if not isinstance(record, dict) or not valid_identity(record.get("source_identity")):
        raise MediaIdentityError("Processing did not produce source provenance")
    sidecar = provenance_path(publication.destination)
    # Hold both leases before publishing media. A crash between publications leaves
    # a missing/stale sidecar, detected by the recorded output digest at use time.
    with Publication(publication.root, sidecar, overwrite=True,
                     cancellation=publication.cancellation) as metadata:
        with publication.stage.open("rb") as stream:
            record = {**record, "output_sha256": hash_stream(stream, cancellation=publication.cancellation)}
        if not valid_provenance(record):
            raise MediaIdentityError("Processing produced incomplete provenance; output was not published")
        metadata.stage.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        publication.publish(lambda _: censor.verify_output())
        metadata.publish(lambda path: read_record(path))


def verify_finished(source_identity: dict, output: Path) -> dict:
    """Explicit-use check; never called from polling or startup."""
    record = read_record(provenance_path(output))
    if not valid_provenance(record):
        raise MediaIdentityError("The finished copy has incomplete or unsupported provenance")
    require_identity(record, source_identity)
    with locked_file(RootBinding.capture(output.parent), output):
        with output.open("rb") as stream:
            if hash_stream(stream) != record.get("output_sha256"):
                raise MediaIdentityError("The finished copy does not match its provenance. Keep it for review or explicitly recreate it.")
    return record
