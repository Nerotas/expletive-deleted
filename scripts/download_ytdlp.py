#!/usr/bin/env python3
"""Download the user-approved, pinned yt-dlp Windows executable."""

from __future__ import annotations

import argparse
import hashlib
import urllib.request
from pathlib import Path

from backend.runtime.dependencies import YTDLP_RELEASE_URL, YTDLP_VERSION
from backend.runtime.environment import get_managed_ytdlp_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root")
    parser.add_argument("--version", default=YTDLP_VERSION)
    args = parser.parse_args(argv)
    if args.version != YTDLP_VERSION:
        raise ValueError("Only the application-approved yt-dlp version may be installed")
    destination = get_managed_ytdlp_path(Path(args.root).resolve() if args.root else None)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".partial")
    try:
        with urllib.request.urlopen(YTDLP_RELEASE_URL, timeout=60) as response, temporary.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        if temporary.stat().st_size == 0:
            raise RuntimeError("yt-dlp download was empty")
        with urllib.request.urlopen(f"https://github.com/yt-dlp/yt-dlp/releases/download/{YTDLP_VERSION}/SHA2-256SUMS", timeout=60) as response:
            checksums = response.read().decode("utf-8")
        expected = next((line.split()[0] for line in checksums.splitlines() if line.rstrip().endswith("yt-dlp.exe")), None)
        actual = hashlib.sha256(temporary.read_bytes()).hexdigest()
        if not expected or actual.casefold() != expected.casefold():
            raise RuntimeError("yt-dlp download checksum did not match the official release")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())