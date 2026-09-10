#!/usr/bin/env python3
"""Download the user-approved, pinned Deno runtime yt-dlp uses to solve YouTube's JavaScript challenge."""

from __future__ import annotations

import argparse
import hashlib
import urllib.request
import zipfile
from pathlib import Path

from backend.runtime.dependencies import DENO_CHECKSUM_URL, DENO_RELEASE_URL, DENO_VERSION
from backend.runtime.environment import get_managed_deno_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root")
    parser.add_argument("--version", default=DENO_VERSION)
    args = parser.parse_args(argv)
    if args.version != DENO_VERSION:
        raise ValueError("Only the application-approved Deno version may be installed")
    destination = get_managed_deno_path(Path(args.root).resolve() if args.root else None)
    destination.parent.mkdir(parents=True, exist_ok=True)
    archive = destination.parent / "deno.zip.partial"
    try:
        with urllib.request.urlopen(DENO_RELEASE_URL, timeout=60) as response, archive.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        if archive.stat().st_size == 0:
            raise RuntimeError("Deno download was empty")
        with urllib.request.urlopen(DENO_CHECKSUM_URL, timeout=60) as response:
            expected = response.read().decode("utf-8").split()[0]
        actual = hashlib.sha256(archive.read_bytes()).hexdigest()
        if actual.casefold() != expected.casefold():
            raise RuntimeError("Deno download checksum did not match the official release")
        temporary = destination.with_suffix(".partial")
        try:
            with zipfile.ZipFile(archive) as bundle:
                with bundle.open("deno.exe") as entry, temporary.open("wb") as output:
                    while chunk := entry.read(1024 * 1024):
                        output.write(chunk)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
    finally:
        archive.unlink(missing_ok=True)
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
