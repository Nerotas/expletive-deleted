"""Build inspectable installation plans without executing their commands."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
from dataclasses import replace
from pathlib import Path
from backend.runtime.locations import (
    get_application_runtime_root,
    get_managed_ffmpeg_directory,
    get_whisper_cache_dir,
)
from .dependency_inspection import (
    inspect_python_dependencies,
)
from backend.runtime.dependency_errors import DependencyPlanError
from .dependency_models import InstallAction, InstallPlan
from .dependency_specs import (
    DENO_RELEASE_URL,
    DENO_VERSION,
    FFMPEG_VERSION,
    PYTHON_REQUIREMENTS,
    STATIC_FFMPEG_VERSION,
    WHISPER_LIBRARIES,
    WHISPER_MODELS,
    WHISPER_MODEL_ID,
    WHISPER_MODEL_REVISION,
    WHISPER_MODEL_SIZE_BYTES,
    YTDLP_RELEASE_URL,
    YTDLP_VERSION,
    _python_dependencies_for_library,
    _python_requirements_for_library,
    _whisper_dependency_id,
)


def _plan_id(actions: tuple[InstallAction, ...]) -> str:
    # Approval covers destinations and commands as well as the displayed component.
    payload = [
        {
            "id": action.id,
            "dependencies": action.dependency_ids,
            "kind": action.kind,
            "source": action.source_url,
            "command": action.command,
            "bytes": action.estimated_download_bytes,
            "component": action.component,
            "version": action.version,
            "purpose": action.purpose,
            "license": action.license,
            "network": action.requires_network,
            "destination": str(action.destination) if action.destination else None,
        }
        for action in actions
    ]
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return digest[:16]


def build_install_plan(
    components: tuple[str, ...] | list[str],
    *,
    python_executable: Path | None = None,
    cache_dir: Path | None = None,
    runtime_root: Path | None = None,
    python_packages_directory: Path | None = None,
    platform_name: str | None = None,
    whisper_library: str = "faster-whisper",
    whisper_model: str = "large-v3",
) -> InstallPlan:
    """Build an inspectable plan without running commands or using the network."""
    requested = tuple(dict.fromkeys(components))
    unknown = sorted(set(requested) - {"ffmpeg", "python", "whisper_model", "ytdlp", "js_runtime"})
    if unknown:
        raise DependencyPlanError(f"Unknown dependency component(s): {', '.join(unknown)}")
    if whisper_library not in WHISPER_LIBRARIES:
        raise DependencyPlanError(f"Unsupported Whisper library: {whisper_library}")
    if whisper_model not in WHISPER_MODELS:
        raise DependencyPlanError(f"Unsupported Whisper model: {whisper_model}")

    python_executable = (python_executable or Path(sys.executable)).resolve()
    cache_dir = (cache_dir or get_whisper_cache_dir()).resolve()
    runtime_root = (runtime_root or get_application_runtime_root()).resolve()
    configured_python_packages = os.environ.get("CENSOR_PYTHON_PACKAGES_DIR", "").strip()
    python_packages_directory = (
        python_packages_directory
        or (Path(configured_python_packages) if configured_python_packages else None)
    )
    if python_packages_directory is not None:
        python_packages_directory = python_packages_directory.expanduser().resolve()
    python_package_destination = python_packages_directory or python_executable.parent
    pip_target_arguments = (
        ("--upgrade", "--target", str(python_packages_directory))
        if python_packages_directory is not None
        else ()
    )
    platform_name = platform_name or platform.system()
    actions: list[InstallAction] = []
    python_dependencies_ready = all(
        status.ready for status in inspect_python_dependencies(whisper_library)
    )

    if "ffmpeg" in requested:
        actions.append(
            InstallAction(
                id="install-static-ffmpeg-package",
                dependency_ids=(),
                kind="command",
                description="Install the approved cross-platform FFmpeg runtime manager",
                source_name="Python Package Index / static-ffmpeg",
                source_url="https://pypi.org/project/static-ffmpeg/",
                command=(
                    str(python_executable),
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    *pip_target_arguments,
                    f"static-ffmpeg=={STATIC_FFMPEG_VERSION}",
                ),
                destination=python_package_destination,
            )
        )

        actions.append(
            InstallAction(
                id="download-managed-ffmpeg-runtime",
                dependency_ids=("ffmpeg", "ffprobe"),
                kind="command",
                description="Download and verify the approved FFmpeg and FFprobe runtime",
                source_name="static-ffmpeg platform binaries",
                source_url="https://pypi.org/project/static-ffmpeg/",
                command=(
                    str(python_executable),
                    "-m",
                    "scripts.download_ffmpeg_runtime",
                    "--root",
                    str(runtime_root),
                ),
                destination=get_managed_ffmpeg_directory(runtime_root),
            )
        )

    if "ytdlp" in requested:
        if platform_name != "Windows":
            raise DependencyPlanError("Managed yt-dlp download is currently supported on Windows only")
        actions.append(
            InstallAction(
                id="download-managed-ytdlp",
                dependency_ids=("ytdlp",),
                kind="command",
                description="Download and verify the approved yt-dlp YouTube downloader",
                source_name="yt-dlp official GitHub release",
                source_url=YTDLP_RELEASE_URL,
                command=(str(python_executable), "-m", "scripts.download_ytdlp", "--root", str(runtime_root), "--version", YTDLP_VERSION),
                destination=runtime_root / "dependencies" / "yt-dlp",
            )
        )

    if "js_runtime" in requested:
        if platform_name != "Windows":
            raise DependencyPlanError("Managed Deno download is currently supported on Windows only")
        actions.append(
            InstallAction(
                id="download-managed-deno-runtime",
                dependency_ids=("js_runtime",),
                kind="command",
                description="Download and verify the approved JavaScript runtime (Deno) that yt-dlp uses for YouTube downloads",
                source_name="Deno official GitHub release",
                source_url=DENO_RELEASE_URL,
                command=(str(python_executable), "-m", "scripts.download_deno_runtime", "--root", str(runtime_root), "--version", DENO_VERSION),
                destination=runtime_root / "dependencies" / "deno",
            )
        )

    if "python" in requested or (
        "whisper_model" in requested and not python_dependencies_ready
    ):
        requirements = _python_requirements_for_library(whisper_library)
        dependency_ids = [
            f"python:{distribution}"
            for distribution, _version in _python_dependencies_for_library(whisper_library)
        ]
        actions.append(
            InstallAction(
                id="install-python-dependencies",
                dependency_ids=tuple(dependency_ids),
                kind="command",
                description="Install the tested Python dependency versions",
                source_name="Python Package Index",
                source_url="https://pypi.org/",
                command=(
                    str(python_executable),
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    *pip_target_arguments,
                    *requirements,
                ),
                destination=python_package_destination,
            )
        )

    if "whisper_model" in requested:
        model_dependency_id = _whisper_dependency_id(whisper_library, whisper_model)
        source_name = "Hugging Face / Systran"
        source_url = (
            f"https://huggingface.co/{WHISPER_MODEL_ID}/tree/{WHISPER_MODEL_REVISION}"
            if whisper_model == "large-v3"
            else f"https://huggingface.co/Systran/faster-whisper-{whisper_model}"
        )
        actions.append(
            InstallAction(
                id=f"download-{whisper_library}-{whisper_model}",
                dependency_ids=(model_dependency_id,),
                kind="model_download",
                description=f"Download the {whisper_library} {whisper_model} model",
                source_name=source_name,
                source_url=source_url,
                command=(
                    str(python_executable),
                    "-m",
                    "scripts.download_whisper_model",
                    "--cache-dir",
                    str(cache_dir),
                    "--model",
                    whisper_model,
                ),
                estimated_download_bytes=(
                    WHISPER_MODEL_SIZE_BYTES
                    if whisper_model == "large-v3"
                    else None
                ),
                progress_path=cache_dir,
                destination=cache_dir,
            )
        )

    metadata = {
        "install-static-ffmpeg-package": {
            "component": "ffmpeg",
            "version": STATIC_FFMPEG_VERSION,
            "purpose": "Install the approved FFmpeg runtime manager used to obtain FFmpeg and FFprobe.",
            "license": "MIT",
        },
        "download-managed-ffmpeg-runtime": {
            "component": "ffmpeg",
            "version": FFMPEG_VERSION,
            "purpose": "Download FFmpeg and FFprobe for local media processing.",
            "license": "GPL-3.0-or-later",
        },
        "download-managed-ytdlp": {
            "component": "ytdlp",
            "version": YTDLP_VERSION,
            "purpose": "Download individual YouTube videos into the local media library.",
            "license": "Unlicense",
        },
        "download-managed-deno-runtime": {
            "component": "js_runtime",
            "version": DENO_VERSION,
            "purpose": "Provide the JavaScript runtime yt-dlp uses for YouTube challenge solving.",
            "license": "MIT",
        },
        "install-python-dependencies": {
            "component": "python",
            "version": ", ".join(PYTHON_REQUIREMENTS),
            "purpose": "Install the pinned transcription and local processing Python packages.",
            "license": "MIT/BSD-3-Clause/Apache-2.0 and bundled dependency notices",
        },
    }
    action_tuple = tuple(
        replace(action, **metadata.get(action.id, {
            "component": "whisper_model",
            "version": whisper_model,
            "purpose": "Download the selected Whisper speech model for local transcription.",
            "license": "MIT",
        }))
        for action in actions
    )
    if not action_tuple:
        raise DependencyPlanError("At least one dependency component is required")
    return InstallPlan(
        id=_plan_id(action_tuple),
        actions=action_tuple,
        whisper_library=whisper_library,
        whisper_model=whisper_model,
    )
