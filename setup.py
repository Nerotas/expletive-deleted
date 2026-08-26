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

from workflow_runtime import (
    find_ffmpeg,
    find_ffprobe,
    format_bytes,
    get_directory_size,
    get_external_whisper_cache_dir,
    get_runtime_paths,
    get_whisper_cache_dir,
)


PROJECT_ROOT = Path(__file__).resolve().parent
VENV_PYTHON = PROJECT_ROOT / ".venv" / (
    "Scripts/python.exe" if platform.system() == "Windows" else "bin/python"
)


def find_winget() -> str | None:
    """Find winget even when its WindowsApps alias is absent from PATH."""
    winget = shutil.which("winget")
    if winget:
        return winget
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None
    alias = Path(local_app_data) / "Microsoft" / "WindowsApps" / "winget.exe"
    return str(alias) if alias.is_file() else None


def system_install_command() -> list[str] | None:
    """Return the supported FFmpeg installation command for this platform."""
    if platform.system() == "Windows":
        if winget := find_winget():
            return [winget, "install", "--id", "Gyan.FFmpeg.Shared", "-e"]
        if choco := shutil.which("choco"):
            return [choco, "install", "ffmpeg", "-y"]
    elif platform.system() == "Darwin" and shutil.which("brew"):
        return ["brew", "install", "ffmpeg"]
    return None


def ffmpeg_guidance() -> str:
    if platform.system() == "Windows":
        if find_winget():
            return "Install FFmpeg with: winget install --id Gyan.FFmpeg.Shared -e"
        if shutil.which("choco"):
            return "Install FFmpeg with: choco install ffmpeg -y"
        return "Install FFmpeg with: winget install --id Gyan.FFmpeg.Shared -e"
    if platform.system() == "Darwin":
        return "Install FFmpeg with: brew install ffmpeg"
    return "Install FFmpeg with your package manager, for example: sudo apt install ffmpeg"


def run(command: list[str]) -> int:
    print("+", " ".join(command))
    return subprocess.run(command, cwd=PROJECT_ROOT, check=False).returncode


def print_venv_whisper_profile() -> None:
    """Report the profile available through the initialized faster-whisper environment."""
    command = (
        "from workflow_runtime import get_whisper_device_status; "
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--install-system-dependencies",
        action="store_true",
        help="Install FFmpeg with the detected package manager.",
    )
    args = parser.parse_args()

    if sys.version_info < (3, 9):
        print("Python 3.9 or later is required.")
        return 1

    paths = get_runtime_paths()
    paths.create()
    print(f"Created workflow folders in: {paths.root}")
    whisper_cache_dir = get_whisper_cache_dir(paths.root)
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

    if run([str(VENV_PYTHON), "-m", "pip", "install", "--upgrade", "pip"]) != 0:
        return 1
    if run([str(VENV_PYTHON), "-m", "pip", "install", "-r", "requirements.txt"]) != 0:
        return 1

    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        print("FFmpeg was not found on PATH.")
        if args.install_system_dependencies:
            command = system_install_command()
            if command:
                if run(command) != 0:
                    return 1
                ffmpeg = find_ffmpeg()
                ffprobe = find_ffprobe()
                if ffmpeg and ffprobe:
                    print(f"FFmpeg installation completed. Found: {ffmpeg}")
                    print(f"FFprobe installation completed. Found: {ffprobe}")
                    print(f"Bootstrap complete. Run: {VENV_PYTHON} diagnostics.py")
                    return 0
                print("FFmpeg installation completed, but the binaries are not yet discoverable.")
                print("If you expect winget aliases, open a new terminal and rerun setup.")
                return 0
            print("No supported package manager was detected.")
        print(ffmpeg_guidance())
        return 1

    print(f"FFmpeg found: {ffmpeg}")
    print_venv_whisper_profile()
    print(f"Bootstrap complete. Run: {VENV_PYTHON} diagnostics.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())