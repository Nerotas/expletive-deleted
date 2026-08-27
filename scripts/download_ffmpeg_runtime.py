#!/usr/bin/env python3
"""Fetch the user-approved static-ffmpeg runtime and record its executable paths."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.runtime.environment import get_managed_ffmpeg_manifest_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root")
    args = parser.parse_args(argv)

    try:
        from static_ffmpeg import run
    except ImportError as exc:
        raise RuntimeError("static-ffmpeg must be installed before downloading FFmpeg") from exc

    ffmpeg, ffprobe = run.get_or_fetch_platform_executables_else_raise()
    manifest_path = get_managed_ffmpeg_manifest_path(Path(args.root) if args.root else None)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps({"ffmpeg": str(Path(ffmpeg).resolve()), "ffprobe": str(Path(ffprobe).resolve())}) + "\n",
        encoding="utf-8",
    )
    print(manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
