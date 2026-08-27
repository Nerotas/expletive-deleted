#!/usr/bin/env python3
"""Inspect and update persistent Profanity Censor settings."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from backend.settings import (
    AppSettings,
    DirectoryAccessError,
    SettingsFileError,
    SettingsStore,
    SettingsValidationError,
    ensure_directories,
    inspect_directories,
    settings_to_dict,
)


def _absolute_path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def _updated_directories(settings: AppSettings, args: argparse.Namespace) -> AppSettings:
    supplied = {
        "input": args.input,
        "output": args.output,
        "archive": args.archive,
        "transcripts": args.transcripts,
    }
    if not any(supplied.values()):
        raise SettingsValidationError(["at least one directory override is required"])

    directories = replace(
        settings.directories,
        **{
            name: _absolute_path(value)
            for name, value in supplied.items()
            if value is not None
        },
    )
    updated = replace(settings, directories=directories)
    updated.validate()
    return updated


def _updated_options(settings: AppSettings, args: argparse.Namespace) -> AppSettings:
    supplied = {
        "mode": args.mode,
        "device": args.device,
        "stereo_method": args.stereo_method,
        "padding_before_ms": args.padding_before_ms,
        "padding_after_ms": args.padding_after_ms,
        "surround_output": args.surround_output,
        "video_mode": args.video_mode,
        "archive_after_success": args.archive_after_success,
    }
    if all(value is None for value in supplied.values()):
        raise SettingsValidationError(["at least one processing option is required"])

    updated = replace(
        settings,
        processing=replace(
            settings.processing,
            **{
                name: value
                for name, value in supplied.items()
                if name in {"mode", "device"} and value is not None
            },
        ),
        censoring=replace(
            settings.censoring,
            **{
                name: value
                for name, value in supplied.items()
                if name in {"stereo_method", "padding_before_ms", "padding_after_ms"}
                and value is not None
            },
        ),
        audio=replace(
            settings.audio,
            **({"surround_output": args.surround_output} if args.surround_output else {}),
        ),
        video=replace(
            settings.video,
            **({"mode": args.video_mode} if args.video_mode else {}),
        ),
        source=replace(
            settings.source,
            **(
                {"archive_after_success": args.archive_after_success}
                if args.archive_after_success is not None
                else {}
            ),
        ),
    )
    updated.validate()
    return updated


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("show", help="Print the persisted settings or defaults")
    subparsers.add_parser("init", help="Persist defaults and create configured directories")
    subparsers.add_parser("validate", help="Check configured directories without changing them")

    set_directories = subparsers.add_parser(
        "set-directories",
        help="Update one or more working directories",
    )
    set_directories.add_argument("--input", help="Ready/input directory")
    set_directories.add_argument("--output", help="Finished/output directory")
    set_directories.add_argument("--archive", help="Processed/archive directory")
    set_directories.add_argument("--transcripts", help="Transcript directory")
    set_directories.add_argument(
        "--create",
        action="store_true",
        help="Create and verify all configured directories before saving",
    )
    set_options = subparsers.add_parser(
        "set-options",
        help="Update Phase 6 processing options",
    )
    set_options.add_argument("--mode", choices=["report_only", "censor"])
    set_options.add_argument("--device", choices=["auto", "cpu", "cuda"])
    set_options.add_argument("--stereo-method", choices=["drop_audio", "karaoke"])
    set_options.add_argument("--padding-before-ms", type=int)
    set_options.add_argument("--padding-after-ms", type=int)
    set_options.add_argument("--surround-output", choices=["preserve_5_1", "downmix_stereo"])
    set_options.add_argument("--video-mode", choices=["h264", "preserve_source"])
    archive = set_options.add_mutually_exclusive_group()
    archive.add_argument(
        "--archive-after-success",
        dest="archive_after_success",
        action="store_true",
    )
    archive.add_argument(
        "--keep-original",
        dest="archive_after_success",
        action="store_false",
    )
    set_options.set_defaults(archive_after_success=None)
    return parser


def main(argv: list[str] | None = None, store: SettingsStore | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    store = store or SettingsStore()

    try:
        settings = store.load()
        if args.command == "show":
            print(json.dumps(settings_to_dict(settings), indent=2))
            print(f"Settings file: {store.path}")
            return 0
        if args.command == "init":
            ensure_directories(settings.directories)
            store.save(settings)
            print(f"Settings initialized: {store.path}")
            return 0
        if args.command == "validate":
            statuses = inspect_directories(settings.directories)
            for status in statuses:
                label = "OK" if status.ready else "FAIL"
                detail = str(status.path) if status.ready else f"{status.path}: {status.error}"
                print(f"[{label}] {status.field}: {detail}")
            return 0 if all(status.ready for status in statuses) else 1
        if args.command == "set-directories":
            updated = _updated_directories(settings, args)
            if args.create:
                ensure_directories(updated.directories)
            store.save(updated)
            print(f"Settings updated: {store.path}")
            return 0
        if args.command == "set-options":
            updated = _updated_options(settings, args)
            store.save(updated)
            print(f"Settings updated: {store.path}")
            return 0
    except (SettingsValidationError, SettingsFileError, DirectoryAccessError) as exc:
        print(f"[FAILED] {exc}")
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())