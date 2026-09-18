"""Advanced command-line adapter for single-file censoring."""

import os
import sys
from pathlib import Path
from contextlib import ExitStack
from backend.filesystem.paths import RootBinding
from backend.filesystem.operations import locked_file
from backend.filesystem.publication import Publication

from .engine import ProfanityCensor


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Transcribe and censor one media file")
    parser.add_argument("input_file")
    parser.add_argument("output_file")
    parser.add_argument("model", nargs="?", default="large", choices=["large"])
    parser.add_argument("transcripts_dir", nargs="?")
    parser.add_argument("--overwrite", action="store_true", help="Explicitly replace the selected output after verification")
    parser.add_argument("--report-only", action="store_true", help="List policy review candidates without changing media")
    parser.add_argument(
        "--include-undiscovered",
        action="store_true",
        help="Also censor vendor-list matches that are not included or excluded",
    )
    parser.add_argument(
        "--censor-method",
        default="mute",
        choices=["mute", "karaoke"],
        help="mute: silence profane intervals (default); karaoke: cancel centre-panned audio",
    )
    parser.add_argument("--padding-before-ms", type=int, default=150)
    parser.add_argument("--padding-after-ms", type=int, default=150)
    parser.add_argument(
        "--surround-output",
        choices=["preserve_5_1", "downmix_stereo"],
        default="preserve_5_1",
    )
    parser.add_argument(
        "--video-mode",
        choices=["h264", "preserve_source"],
        default="preserve_source",
    )
    args = parser.parse_args()

    input_file = args.input_file
    output_file = args.output_file
    required_model = args.model
    transcripts_dir = args.transcripts_dir

    if not os.path.exists(input_file):
        print(f"[-] Input file not found: {input_file}")
        sys.exit(1)

    print("=" * 70)
    print("  Profanity Censoring Workflow")
    print("=" * 70)
    print(f"Input:  {input_file}")
    print(f"Output: {output_file}")
    print(f"Model:  {required_model}")
    if transcripts_dir:
        print(f"Transcripts: {transcripts_dir}")
    if args.report_only and args.include_undiscovered:
        parser.error("--report-only and --include-undiscovered cannot be used together")
    if args.report_only:
        print("Mode:   report-only (no media output or archival)")
    elif args.include_undiscovered:
        print("Mode:   censoring configured and undiscovered vendor-list words")
    print()

    source, destination = Path(input_file).absolute(), Path(output_file).absolute()
    try:
        with ExitStack() as resources:
            resources.enter_context(locked_file(RootBinding.capture(source.parent), source))
            publication = None if args.report_only else resources.enter_context(Publication(
                RootBinding.capture(destination.parent), destination, source=source, overwrite=args.overwrite))
            censor = ProfanityCensor(
                input_file,
                str(publication.stage if publication else destination),
                required_model,
                transcripts_dir,
                censor_method=args.censor_method,
                padding_before_ms=args.padding_before_ms,
                padding_after_ms=args.padding_after_ms,
                surround_output=args.surround_output,
                video_mode=args.video_mode,
            )
            success = censor.process(
                report_only=args.report_only,
                include_undiscovered=args.include_undiscovered,
            )

            if success and publication:
                publication.publish(lambda _: censor.verify_output())
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"[FAILED] {exc}")
        success = False

    print()
    if success:
        print("[OK] Processing complete!")
        sys.exit(0)
    else:
        print("[FAILED] Processing failed!")
        sys.exit(1)
