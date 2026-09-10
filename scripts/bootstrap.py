#!/usr/bin/env python3
"""Bootstrap a portable local environment for the profanity workflow."""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from backend.runtime import (
    DependencyInstallError,
    PROJECT_ROOT,
    build_install_plan,
    execute_install_plan,
    find_ffmpeg,
    find_ffprobe,
    format_bytes,
    get_directory_size,
    get_external_whisper_cache_dir,
    get_whisper_cache_dir,
    inspect_dependencies,
)
from backend.runtime.environment import (
    get_application_runtime_root,
    get_managed_deno_path,
    get_managed_ytdlp_path,
)
from backend.settings import (
    DirectoryAccessError,
    SettingsFileError,
    SettingsStore,
    ensure_directories,
    load_effective_settings,
)


VENV_PYTHON = PROJECT_ROOT / ".venv" / (
    "Scripts/python.exe" if platform.system() == "Windows" else "bin/python"
)


def system_install_command() -> list[str] | None:
    """Legacy bootstrap leaves approved FFmpeg retrieval to the dependency-plan UI."""
    return None


def ffmpeg_guidance() -> str:
    return "Review an install plan with: python manage_dependencies.py plan --component ffmpeg"


def run(command: list[str]) -> int:
    print("+", " ".join(command))
    return subprocess.run(command, cwd=PROJECT_ROOT, check=False).returncode


def python_version_supported() -> bool:
    return sys.version_info >= (3, 9)


def print_venv_whisper_profile() -> None:
    """Report the profile available through the initialized faster-whisper environment."""
    command = (
        "from backend.runtime import get_whisper_device_status; "
        "status = get_whisper_device_status(); "
        "print(f'Whisper profile: {status.selected} ({status.compute_type}) - {status.detail}')"
    )
    result = subprocess.run(
        [str(VENV_PYTHON), "-c", command],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        print(result.stdout.strip())
    else:
        print("Whisper profile: unavailable; it will be detected when processing starts.")


def initialize_application_settings(store: SettingsStore | None = None) -> tuple[Path, tuple[Path, ...]]:
    """Persist defaults when needed and create the effective working directories."""
    store = store or SettingsStore()
    persisted_settings = store.load()
    effective_settings = load_effective_settings(store)
    statuses = ensure_directories(effective_settings.directories)
    if not store.path.exists():
        store.save(persisted_settings)
    return store.path, tuple(status.path for status in statuses)


def _development_runtime_components() -> list[str]:
    inventory = inspect_dependencies(
        get_whisper_cache_dir(),
        ytdlp_bin=get_managed_ytdlp_path(),
        js_runtime_bin=get_managed_deno_path(),
    )
    missing: list[str] = []
    if not inventory.ffmpeg.ready or not inventory.ffprobe.ready:
        missing.append("ffmpeg")
    if not inventory.ytdlp.ready:
        missing.append("ytdlp")
    if not inventory.js_runtime.ready:
        missing.append("js_runtime")
    return missing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--install-system-dependencies",
        action="store_true",
        help="Show the development-runtime installation plan without installing it.",
    )
    parser.add_argument(
        "--install-approved-runtime",
        action="store_true",
        help="Prompt before installing and verifying all missing development-runtime components.",
    )
    args = parser.parse_args()

    if not python_version_supported():
        print("Python 3.9 or later is required.")
        return 1

    try:
        settings_path, working_directories = initialize_application_settings()
    except (SettingsFileError, DirectoryAccessError) as exc:
        print(f"Settings initialization failed: {exc}")
        return 1
    print(f"Settings file: {settings_path}")
    print("Working directories:")
    for working_directory in working_directories:
        print(f"- {working_directory}")

    whisper_cache_dir = get_whisper_cache_dir()
    whisper_cache_dir.mkdir(parents=True, exist_ok=True)
    print(f"Whisper cache path: {whisper_cache_dir}")
    print(f"Whisper cache size: {format_bytes(get_directory_size(whisper_cache_dir))}")
    external_cache_dir = get_external_whisper_cache_dir()
    if external_cache_dir != whisper_cache_dir and external_cache_dir.exists():
        print(
            "External Whisper cache detected: "
            f"{external_cache_dir} ({format_bytes(get_directory_size(external_cache_dir))})"
        )
        print(
            "Tip: migrate or clean it with: "
            f"{VENV_PYTHON} manage_whisper_cache.py migrate --clean-external"
        )

    if not VENV_PYTHON.exists():
        if run([sys.executable, "-m", "venv", str(PROJECT_ROOT / ".venv")]) != 0:
            return 1

    if run([str(VENV_PYTHON), "-m", "pip", "install", "-r", "requirements.txt"]) != 0:
        return 1

    runtime_components = _development_runtime_components()
    ffmpeg = find_ffmpeg()
    ffprobe = find_ffprobe()
    if ffmpeg:
        print(f"FFmpeg found: {ffmpeg}")
    if ffprobe:
        print(f"FFprobe found: {ffprobe}")

    if runtime_components:
        runtime_root = get_application_runtime_root()
        plan = build_install_plan(
            tuple(runtime_components),
            cache_dir=whisper_cache_dir,
            runtime_root=runtime_root,
        )
        joined = " --component ".join(runtime_components)
        print(f"\nManaged development runtime root: {runtime_root}")
        print("Development runtime is not yet ready. Review the exact plan before installing anything:")
        print(f"  {VENV_PYTHON} manage_dependencies.py plan --component {joined}")
        print(f"  {VENV_PYTHON} manage_dependencies.py install --component {joined} --approve PLAN_ID")
        print("Whisper large-v3 remains a separate explicit download:")
        print(f"  {VENV_PYTHON} manage_dependencies.py plan --component whisper_model")
        if args.install_system_dependencies:
            print(f"\nApproved plan ID: {plan.id}")
            print("The plan was displayed only; no installation was started.")
        if args.install_approved_runtime:
            response = input(
                "\nInstall and verify these approved development-runtime components now? [y/N] "
            ).strip().casefold()
            if response not in {"y", "yes"}:
                print("Installation skipped.")
                return 0
            try:
                results = execute_install_plan(
                    plan,
                    approved_plan_id=plan.id,
                    progress_callback=lambda event: print(
                        f"[{event.phase.upper()}] {event.action_id}: {event.message}"
                    ),
                    cache_dir=whisper_cache_dir,
                )
            except DependencyInstallError as exc:
                print(f"Development runtime installation failed: {exc}")
                return 1
            for result in results:
                print(f"[OK] {result.action_id}: {result.detail}")
        return 0

    print_venv_whisper_profile()
    print(f"Bootstrap complete. Run: {VENV_PYTHON} diagnostics.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
