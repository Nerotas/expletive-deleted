#!/usr/bin/env python3
"""Process all supported media in the project ready folder."""

from __future__ import annotations

import argparse
import shutil
import time
from pathlib import Path

from backend.censor import ProfanityCensor, transcript_cache_is_compatible
from backend.runtime import (
    REQUIRED_WHISPER_MODEL,
    find_ffprobe,
    get_runtime_paths,
    get_whisper_cache_dir,
    get_whisper_device_status,
)


MEDIA_EXTENSIONS = {
    ".avi", ".flv", ".m4a", ".mkv", ".mov", ".mp3", ".mp4", ".wav", ".webm", ".wmv",
}
AUDIO_EXTENSIONS = {".m4a", ".mp3", ".wav"}


def format_seconds(seconds: float) -> str:
    whole = max(0, int(round(seconds)))
    hours, remainder = divmod(whole, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def output_path(input_file: Path, output_dir: Path) -> Path:
    extension = ".mp3" if input_file.suffix.lower() in AUDIO_EXTENSIONS else ".mkv"
    return output_dir / f"{input_file.stem}-censored{extension}"


def load_whisper_model(model_name: str):
    """Load the Whisper model once for the entire batch."""
    from faster_whisper import WhisperModel
    status = get_whisper_device_status(model_name)
    device = status.selected
    print(f"[*] Whisper profile: {device} ({status.compute_type}); {status.detail}")
    fw_model_name = ProfanityCensor._MODEL_NAME_MAP.get(model_name, model_name)
    compute_type = status.compute_type
    print(f"[*] Loading Whisper {fw_model_name} on {device} ({compute_type})...")
    load_started = time.perf_counter()
    model = WhisperModel(
        fw_model_name,
        device=device,
        compute_type=compute_type,
        download_root=str(get_whisper_cache_dir()),
    )
    print(f"[*] Model loaded in {format_seconds(time.perf_counter() - load_started)}")
    return model, device


def process_file(
    input_file: Path,
    model_name: str,
    paths,
    index: int,
    total: int,
    report_only: bool = False,
    overwrite: bool = False,
    include_undiscovered: bool = False,
    whisper_model=None,
    censor_method: str = "mute",
) -> tuple[str, set[str], bool, int]:
    started = time.perf_counter()
    destination = output_path(input_file, paths.finished)
    print(f"\n[FILE {index}/{total}] {input_file.name}")
    if report_only:
        print(f"[FILE {index}/{total}] Mode: report-only")
    else:
        print(f"[FILE {index}/{total}] Target: {destination.name}")
    if not report_only and destination.exists() and not overwrite:
        print(f"[SKIP] Output already exists: {destination.name}")
        print(f"[FILE {index}/{total}] Elapsed: {format_seconds(time.perf_counter() - started)}")
        return "skip", set(), False, 0

    if report_only:
        print(f"[REPORT] {input_file.name}")
    elif include_undiscovered:
        print(f"[PROCESS] {input_file.name} (including undiscovered vendor-list matches)")
    elif overwrite and destination.exists():
        print(f"[PROCESS] {input_file.name} (overwriting {destination.name})")
    else:
        print(f"[PROCESS] {input_file.name}")

    try:
        censor = ProfanityCensor(
            str(input_file),
            str(destination),
            model_name,
            str(paths.transcripts),
            whisper_model=whisper_model,
            censor_method=censor_method,
        )
        success = censor.process(report_only=report_only, include_undiscovered=include_undiscovered)
        discovered = {c["word"] for c in censor.review_candidates}
        used_cached = censor.used_cached_transcript
        profane_count = censor.profane_count
    except Exception as exc:
        print(f"[FAILED] {input_file.name}: {exc}")
        print(f"[FILE {index}/{total}] Elapsed: {format_seconds(time.perf_counter() - started)}")
        return "fail", set(), False, 0

    if not success:
        print(f"[FAILED] {input_file.name}")
        print(f"[FILE {index}/{total}] Elapsed: {format_seconds(time.perf_counter() - started)}")
        return "fail", discovered, used_cached, profane_count

    if report_only:
        print(f"[OK] Report complete; source retained: {input_file.name}")
        print(f"[FILE {index}/{total}] Elapsed: {format_seconds(time.perf_counter() - started)}")
        return "ok", discovered, used_cached, profane_count

    if not destination.exists():
        print(f"[FAILED] Output was not created: {destination.name}")
        print(f"[FILE {index}/{total}] Elapsed: {format_seconds(time.perf_counter() - started)}")
        return "fail", discovered, used_cached, profane_count

    shutil.move(str(input_file), paths.processed / input_file.name)
    print(f"[OK] Archived source: {input_file.name}")
    print(f"[FILE {index}/{total}] Elapsed: {format_seconds(time.perf_counter() - started)}")
    return "ok", discovered, used_cached, profane_count


def main() -> int:
    batch_started = time.perf_counter()
    parser = argparse.ArgumentParser(description="Process media from the ready folder")
    parser.add_argument(
        "--model",
        default=REQUIRED_WHISPER_MODEL,
        choices=[REQUIRED_WHISPER_MODEL],
        help="Required for accurate profanity timestamps.",
    )
    parser.add_argument("--list", action="store_true", help="List media without processing it")
    parser.add_argument("--report-only", action="store_true", help="Report potential policy additions without changing media")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing censored output")
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
    args = parser.parse_args()

    if args.report_only and args.include_undiscovered:
        parser.error("--report-only and --include-undiscovered cannot be used together")
    if args.report_only and args.overwrite:
        parser.error("--overwrite cannot be used with --report-only")

    paths = get_runtime_paths()
    paths.create()
    files = sorted(path for path in paths.ready.iterdir() if path.suffix.lower() in MEDIA_EXTENSIONS)
    if args.list:
        print(f"[LIST] Found {len(files)} supported file(s) in {paths.ready}")
        for file in files:
            print(file.name)
        return 0
    if not files:
        print(f"No supported media found in: {paths.ready}")
        return 0

    print("=" * 70)
    print("Batch Profanity Review" if args.report_only else "Batch Profanity Censoring")
    print("=" * 70)
    print(f"Input folder:      {paths.ready}")
    print(f"Finished folder:   {paths.finished}")
    print(f"Processed folder:  {paths.processed}")
    print(f"Transcripts folder:{paths.transcripts}")
    print(f"Whisper model:     {args.model}")
    print(f"Files queued:      {len(files)}")
    if args.report_only:
        print("Mode: report-only; source files will remain in ready/ and no outputs will be created.")
    else:
        if args.overwrite:
            print("Mode: overwrite existing censored outputs.")
        if args.include_undiscovered:
            print("Mode: censor undiscovered vendor-list matches unless they are excluded.")
        print("Note: each file prints a step-by-step runtime estimate before processing.")

    # Load the model once and share it across all files to avoid reloading per file.
    ffprobe_bin = find_ffprobe()
    needs_transcription = ffprobe_bin is None or any(
        not transcript_cache_is_compatible(
            str(file),
            str(paths.transcripts / f"{file.stem}-transcript.json"),
            ffprobe_bin,
        )
        for file in files
    )
    whisper_model = load_whisper_model(args.model) if needs_transcription else None
    if whisper_model is None:
        print("[*] All transcripts cached; skipping model load.")

    ok_count = 0
    skip_count = 0
    failed = 0
    fresh_transcripts = 0
    cached_transcripts = 0
    censored_count = 0
    clean_count = 0
    all_discovered: set[str] = set()
    interrupted = False
    try:
        for index, input_file in enumerate(files, start=1):
            status, discovered, used_cached, profane_count = process_file(
                input_file,
                args.model,
                paths,
                index,
                len(files),
                args.report_only,
                args.overwrite,
                args.include_undiscovered,
                whisper_model=whisper_model,
                censor_method=args.censor_method,
            )
            all_discovered.update(discovered)
            if status == "ok":
                ok_count += 1
                if used_cached:
                    cached_transcripts += 1
                else:
                    fresh_transcripts += 1
                if profane_count > 0:
                    censored_count += 1
                else:
                    clean_count += 1
            elif status == "skip":
                skip_count += 1
            else:
                failed += 1
    except KeyboardInterrupt:
        interrupted = True
        print("\n[!] Batch stopped at your request. No further files will be processed.")
    elapsed = format_seconds(time.perf_counter() - batch_started)
    print("\n" + "=" * 70)
    print("Batch Summary")
    print("-" * 70)
    print(f"  Status:             {'Interrupted after' if interrupted else 'Completed in'} {elapsed}")
    print(f"  Files queued:       {len(files)}")
    print(f"  Processed:          {ok_count + failed}")
    if not args.report_only:
        print(f"    Transcribed fresh:  {fresh_transcripts}")
        print(f"    Loaded from cache:  {cached_transcripts}")
        print(f"    Censored:           {censored_count}")
        print(f"    Copied clean:       {clean_count}")
    print(f"  Skipped:            {skip_count}")
    print(f"  Failed:             {failed}")
    if all_discovered:
        print(f"\nDiscovered potential words ({len(all_discovered)} unique):")
        for word in sorted(all_discovered):
            print(f"  {word}")
        print(
            "Add to resources/profanity_censor_words.txt to censor, "
            "or resources/profanity_exclusions.txt to ignore."
        )
    else:
        print("\nNo undiscovered potential words found across all files.")
    return 1 if interrupted or failed else 0


if __name__ == "__main__":
    raise SystemExit(main())