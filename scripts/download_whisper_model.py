#!/usr/bin/env python3
"""Download a user-selected Whisper model in a child process."""

from __future__ import annotations

import argparse
from pathlib import Path

from backend.runtime.dependencies import (
    WHISPER_LIBRARIES,
    WHISPER_MODELS,
    WHISPER_MODEL_ID,
    WHISPER_MODEL_REVISION,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", required=True)
    parser.add_argument("--library", choices=WHISPER_LIBRARIES, default="faster-whisper")
    parser.add_argument("--model", choices=WHISPER_MODELS, default="large-v3")
    args = parser.parse_args(argv)

    if args.library == "openai-whisper":
        import whisper

        whisper.load_model(args.model, download_root=args.cache_dir)
        model_path = str(Path(args.cache_dir) / Path(whisper._MODELS[args.model]).name)
    else:
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
