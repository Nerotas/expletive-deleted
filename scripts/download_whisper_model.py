#!/usr/bin/env python3
"""Download a user-selected Whisper model in a child process."""

from __future__ import annotations

import argparse

from backend.runtime.dependencies import (
    WHISPER_MODELS,
    WHISPER_MODEL_ID,
    WHISPER_MODEL_REVISION,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", required=True)
    parser.add_argument("--model", choices=WHISPER_MODELS, default="large-v3")
    args = parser.parse_args(argv)

    from faster_whisper.utils import download_model

    model_path = download_model(
        WHISPER_MODEL_ID if args.model == "large-v3" else args.model,
        cache_dir=args.cache_dir,
        revision=WHISPER_MODEL_REVISION if args.model == "large-v3" else None,
    )
    print(model_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
