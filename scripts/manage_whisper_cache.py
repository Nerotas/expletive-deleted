#!/usr/bin/env python3
"""Manage repository-local Whisper model cache files."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from backend.runtime import (
    format_bytes,
    get_directory_size,
    get_external_whisper_cache_dir,
    get_project_root,
    get_whisper_cache_dir,
    REQUIRED_WHISPER_MODEL,
)


MODEL_ALIASES = {
    "large": {"large", "large-v3", "large-v3.pt"},
    "turbo": {"turbo", "large-v3-turbo", "large-v3-turbo.pt"},
}


def configured_model_name() -> str:
    return REQUIRED_WHISPER_MODEL


def print_cache_summary(repo_cache: Path, external_cache: Path, preferred_model: str) -> None:
    print(f"Repo cache:     {repo_cache}")
    print(f"Repo cache size:{format_bytes(get_directory_size(repo_cache))}")
    print(f"Preferred model:{preferred_model}")
    if repo_cache.exists():
        files = sorted(repo_cache.glob("*.pt"))
        if files:
            print("Repo models:")
            for model_file in files:
                print(f"- {model_file.name} ({format_bytes(model_file.stat().st_size)})")
        else:
            print("Repo models:    none")
    else:
        print("Repo models:    cache folder missing")

    print(f"External cache: {external_cache}")
    if external_cache.exists():
        print(f"External size:  {format_bytes(get_directory_size(external_cache))}")
    else:
        print("External size:  missing")


def migrate_external_cache(external_cache: Path, repo_cache: Path, clean_external: bool) -> int:
    if not external_cache.exists():
        print("No external Whisper cache found.")
        return 0

    repo_cache.mkdir(parents=True, exist_ok=True)
    moved = 0
    skipped = 0
    for source in sorted(external_cache.glob("*.pt")):
        destination = repo_cache / source.name
        if destination.exists():
            skipped += 1
            print(f"[SKIP] Already present: {destination.name}")
            continue
        shutil.move(str(source), str(destination))
        moved += 1
        print(f"[MOVE] {source.name} -> {destination}")

    print(f"Moved {moved} model(s); skipped {skipped} existing model(s).")
    if clean_external:
        cleanup_external_cache(external_cache)
    return 0


def cleanup_external_cache(external_cache: Path) -> int:
    if not external_cache.exists():
        print("No external Whisper cache found.")
        return 0

    deleted = 0
    for entry in sorted(external_cache.iterdir()):
        if entry.is_file():
            entry.unlink()
            deleted += 1
            print(f"[DELETE] {entry}")
        elif entry.is_dir():
            shutil.rmtree(entry)
            deleted += 1
            print(f"[DELETE] {entry}")
    try:
        external_cache.rmdir()
        print(f"[DELETE] {external_cache}")
    except OSError:
        pass
    print(f"Removed {deleted} external cache item(s).")
    return 0


def prune_unused_models(repo_cache: Path, preferred_model: str) -> int:
    if not repo_cache.exists():
        print("Repo cache does not exist; nothing to prune.")
        return 0

    aliases = MODEL_ALIASES.get(preferred_model, {preferred_model, f"{preferred_model}.pt"})
    deleted = 0
    kept = 0
    for model_file in sorted(repo_cache.glob("*.pt")):
        if model_file.name in aliases or model_file.stem in aliases:
            kept += 1
            print(f"[KEEP] {model_file.name}")
            continue
        model_file.unlink()
        deleted += 1
        print(f"[DELETE] {model_file.name}")

    print(f"Pruned {deleted} model(s); kept {kept} model(s).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status", help="Show repo and external Whisper cache usage")

    migrate = subparsers.add_parser("migrate", help="Move external Whisper models into the repo cache")
    migrate.add_argument("--clean-external", action="store_true", help="Delete the external cache after migration")

    prune = subparsers.add_parser("prune-unused", help="Delete repo-cached Whisper models not matching the configured model")
    prune.add_argument("--model", help="Override the model name to keep")

    subparsers.add_parser("cleanup-external", help="Delete the external Whisper cache directory")

    args = parser.parse_args()

    project_root = get_project_root()
    repo_cache = get_whisper_cache_dir(project_root)
    external_cache = get_external_whisper_cache_dir()
    preferred_model = configured_model_name()

    if args.command == "status":
        print_cache_summary(repo_cache, external_cache, preferred_model)
        return 0
    if args.command == "migrate":
        return migrate_external_cache(external_cache, repo_cache, args.clean_external)
    if args.command == "prune-unused":
        return prune_unused_models(repo_cache, args.model or preferred_model)
    if args.command == "cleanup-external":
        return cleanup_external_cache(external_cache)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
