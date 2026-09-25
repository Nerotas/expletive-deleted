"""Synthetic identity records for tests that stub transcription and codecs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from backend.media_identity import provenance_path


def identity(payload: bytes = b"source") -> dict:
    return {"algorithm": "sha256", "digest": hashlib.sha256(payload).hexdigest(), "size_bytes": len(payload)}


def provenance(source: Path, output: Path | None = None) -> dict:
    result = {"schema_version": 1, "source_identity": identity(source.read_bytes()),
              "transcript_sha256": hashlib.sha256(b"synthetic transcript").hexdigest(), "processing": {}}
    if output is not None:
        result["output_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
        provenance_path(output).write_text(json.dumps(result), encoding="utf-8")
    return result
