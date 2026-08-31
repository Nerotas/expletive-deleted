#!/usr/bin/env python3
"""Fetch the user-approved static-ffmpeg runtime and record its executable paths."""

from __future__ import annotations

import argparse
import json
import shutil
from uuid import uuid4
from pathlib import Path

from backend.runtime.environment import (
    get_application_runtime_root,
    get_managed_ffmpeg_directory,
    get_managed_ffmpeg_manifest_path,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root")
    args = parser.parse_args(argv)

    try:
        from static_ffmpeg import run
    except ImportError as exc:
        raise RuntimeError("static-ffmpeg must be installed before downloading FFmpeg") from exc

    runtime_root = Path(args.root).expanduser().resolve() if args.root else get_application_runtime_root()
    fetched_ffmpeg, fetched_ffprobe = run.get_or_fetch_platform_executables_else_raise()
    install_directory = get_managed_ffmpeg_directory(runtime_root) / "bin"
    install_directory.mkdir(parents=True, exist_ok=True)
    installed: list[Path] = []
    for source_value in (fetched_ffmpeg, fetched_ffprobe):
        source = Path(source_value).expanduser().resolve()
        destination = install_directory / source.name
        temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.partial")
        try:
            shutil.copy2(source, temporary)
            temporary.replace(destination)
            installed.append(destination.resolve())
        finally:
            temporary.unlink(missing_ok=True)

    ffmpeg, ffprobe = installed
    manifest_path = get_managed_ffmpeg_manifest_path(runtime_root)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps({"ffmpeg": str(Path(ffmpeg).resolve()), "ffprobe": str(Path(ffprobe).resolve())}) + "\n",
        encoding="utf-8",
    )
    print(manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
