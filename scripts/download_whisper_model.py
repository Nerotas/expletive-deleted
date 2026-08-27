#!/usr/bin/env python3
"""Download the approved pinned faster-whisper model in a child process."""

from __future__ import annotations

import argparse

from backend.runtime.dependencies import WHISPER_MODEL_ID, WHISPER_MODEL_REVISION


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", required=True)
    args = parser.parse_args(argv)

    from faster_whisper.utils import download_model

    model_path = download_model(
        WHISPER_MODEL_ID,
        cache_dir=args.cache_dir,
        revision=WHISPER_MODEL_REVISION,
    )
    print(model_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())