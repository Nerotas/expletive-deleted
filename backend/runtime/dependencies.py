"""Structured dependency inventory for application setup workflows."""

from __future__ import annotations

import importlib
import importlib.metadata
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Callable, Literal

from .environment import (
    PROJECT_ROOT,
    find_ffmpeg,
    find_ffprobe,
    get_application_runtime_root,
    get_directory_size,
    get_whisper_cache_dir,
)


DependencyState = Literal["ready", "missing", "invalid"]
InstallKind = Literal["command", "model_download"]

STATIC_FFMPEG_VERSION = "3.0"
FFMPEG_VERSION = "8.0 or later"
FFMPEG_MINIMUM_VERSION = (8, 0)
WHISPER_MODEL_ID = "Systran/faster-whisper-large-v3"
WHISPER_MODEL_REVISION = "edaa852ec7e145841d8ffdb056a99866b5f0a478"
WHISPER_MODEL_SIZE_BYTES = 3_090_835_702
WHISPER_MODEL_FILES = (
    "config.json",
    "model.bin",
    "preprocessor_config.json",
    "tokenizer.json",
    "vocabulary.json",
)
WHISPER_MODELS = ("tiny", "base", "small", "medium", "large-v3")
WHISPER_LIBRARIES = ("faster-whisper", "openai-whisper")
OPENAI_WHISPER_VERSION = "20250625"
OPENAI_WHISPER_NUMPY_VERSION = "2.4.4"
PYTHON_DEPENDENCIES = (
    ("faster-whisper", "1.2.1"),
    ("better-profanity", "0.7.0"),
    ("numpy", "2.5.2"),
    ("ctranslate2", "4.8.1"),
    ("av", "18.1.0"),
    ("huggingface-hub", "1.28.0"),
)
PYTHON_REQUIREMENTS = tuple(f"{name}=={version}" for name, version in PYTHON_DEPENDENCIES)


def _python_dependencies_for_library(
    whisper_library: str,
) -> tuple[tuple[str, str], ...]:
    dependencies = list(PYTHON_DEPENDENCIES)
    if whisper_library == "openai-whisper":
        dependencies = [
            (
                distribution,
                OPENAI_WHISPER_NUMPY_VERSION if distribution == "numpy" else version,
            )
            for distribution, version in dependencies
        ]
        dependencies.append(("openai-whisper", OPENAI_WHISPER_VERSION))
    return tuple(dependencies)


def _python_requirements_for_library(whisper_library: str) -> tuple[str, ...]:
    return tuple(
        f"{distribution}=={version}"
        for distribution, version in _python_dependencies_for_library(whisper_library)
    )


@dataclass(frozen=True)
class DependencyStatus:
    id: str
    name: str
    state: DependencyState
    required_version: str | None
    installed_version: str | None
    path: Path | None
    detail: str
    install_supported: bool

    @property
    def ready(self) -> bool:
        return self.state == "ready"


@dataclass(frozen=True)
class DependencyInventory:
    ffmpeg: DependencyStatus
    ffprobe: DependencyStatus
    python: tuple[DependencyStatus, ...]
    whisper_model: DependencyStatus

    @property
    def ready(self) -> bool:
        return all(
            status.ready
            for status in (self.ffmpeg, self.ffprobe, *self.python, self.whisper_model)
        )

    @property
    def missing(self) -> tuple[DependencyStatus, ...]:
        return tuple(
            status
            for status in (self.ffmpeg, self.ffprobe, *self.python, self.whisper_model)
            if not status.ready
        )


@dataclass(frozen=True)
class InstallAction:
    id: str
    dependency_ids: tuple[str, ...]
    kind: InstallKind
    description: str
    source_name: str
    source_url: str
    command: tuple[str, ...]
    estimated_download_bytes: int | None = None
    progress_path: Path | None = None


@dataclass(frozen=True)
class InstallPlan:
    id: str
    actions: tuple[InstallAction, ...]
    whisper_library: str = "faster-whisper"
    whisper_model: str = "large-v3"


@dataclass(frozen=True)
class InstallProgress:
    action_id: str
    phase: Literal["starting", "running", "verifying", "completed", "cancelled"]
    message: str
    completed_bytes: int | None = None
    total_bytes: int | None = None


@dataclass(frozen=True)
class InstallResult:
    action_id: str
    dependency_ids: tuple[str, ...]
    detail: str


class DependencyPlanError(ValueError):
    """Raised when a dependency install plan cannot be created."""


class DependencyConsentError(PermissionError):
    """Raised unless the caller approves the exact immutable plan."""


class DependencyInstallError(RuntimeError):
    """Raised when installation, cancellation, or verification fails."""


class DependencyNotReadyError(RuntimeError):
    """Raised when processing requests an unprepared dependency."""


def _whisper_dependency_id(library: str, model: str) -> str:
    return "whisper:large-v3" if (library, model) == ("faster-whisper", "large-v3") else f"whisper:{library}:{model}"


def _plan_id(actions: tuple[InstallAction, ...]) -> str:
    payload = [
        {
            "id": action.id,
            "dependencies": action.dependency_ids,
            "kind": action.kind,
            "source": action.source_url,
            "command": action.command,
            "bytes": action.estimated_download_bytes,
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
    platform_name: str | None = None,
    whisper_library: str = "faster-whisper",
    whisper_model: str = "large-v3",
) -> InstallPlan:
    """Build an inspectable plan without running commands or using the network."""
    requested = tuple(dict.fromkeys(components))
    unknown = sorted(set(requested) - {"ffmpeg", "python", "whisper_model"})
    if unknown:
        raise DependencyPlanError(f"Unknown dependency component(s): {', '.join(unknown)}")
    if whisper_library not in WHISPER_LIBRARIES:
        raise DependencyPlanError(f"Unsupported Whisper library: {whisper_library}")
    if whisper_model not in WHISPER_MODELS:
        raise DependencyPlanError(f"Unsupported Whisper model: {whisper_model}")

    python_executable = (python_executable or Path(sys.executable)).resolve()
    cache_dir = (cache_dir or get_whisper_cache_dir()).resolve()
    runtime_root = (runtime_root or get_application_runtime_root()).resolve()
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
                    f"static-ffmpeg=={STATIC_FFMPEG_VERSION}",
                ),
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
                    *requirements,
                ),
            )
        )

    if "whisper_model" in requested:
        model_dependency_id = _whisper_dependency_id(whisper_library, whisper_model)
        if whisper_library == "faster-whisper":
            source_name = "Hugging Face / Systran"
            source_url = (
                f"https://huggingface.co/{WHISPER_MODEL_ID}/tree/{WHISPER_MODEL_REVISION}"
                if whisper_model == "large-v3"
                else f"https://huggingface.co/Systran/faster-whisper-{whisper_model}"
            )
        else:
            source_name = "OpenAI Whisper model repository"
            source_url = "https://github.com/openai/whisper"
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
                    "--library",
                    whisper_library,
                    "--model",
                    whisper_model,
                ),
                estimated_download_bytes=(
                    WHISPER_MODEL_SIZE_BYTES
                    if whisper_library == "faster-whisper" and whisper_model == "large-v3"
                    else None
                ),
                progress_path=cache_dir,
            )
        )

    action_tuple = tuple(actions)
    if not action_tuple:
        raise DependencyPlanError("At least one dependency component is required")
    return InstallPlan(
        id=_plan_id(action_tuple),
        actions=action_tuple,
        whisper_library=whisper_library,
        whisper_model=whisper_model,
    )


def _emit(
    callback: Callable[[InstallProgress], None] | None,
    progress: InstallProgress,
) -> None:
    if callback is not None:
        callback(progress)


def _run_action(
    action: InstallAction,
    cancellation: Event,
    progress_callback: Callable[[InstallProgress], None] | None,
) -> str:
    baseline_size = get_directory_size(action.progress_path) if action.progress_path else 0
    try:
        process = subprocess.Popen(
            action.command,
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        raise DependencyInstallError(f"{action.description} could not start: {exc}") from exc

    try:
        while True:
            if cancellation.is_set():
                raise KeyboardInterrupt

            try:
                stdout, stderr = process.communicate(timeout=0.25)
                break
            except subprocess.TimeoutExpired:
                completed_bytes = None
                if action.progress_path:
                    completed_bytes = max(0, get_directory_size(action.progress_path) - baseline_size)
                _emit(
                    progress_callback,
                    InstallProgress(
                        action.id,
                        "running",
                        f"Fetching component now: {action.description}",
                        completed_bytes=completed_bytes,
                        total_bytes=action.estimated_download_bytes,
                    ),
                )
                time.sleep(0.05)
    except KeyboardInterrupt:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        _emit(progress_callback, InstallProgress(action.id, "cancelled", "Cancelled by user"))
        raise DependencyInstallError(f"{action.description} was cancelled") from None

    if process.returncode != 0:
        detail = (stderr or stdout).strip().splitlines()
        summary = detail[-1] if detail else f"exit code {process.returncode}"
        raise DependencyInstallError(f"{action.description} failed: {summary}")
    return (stdout or stderr).strip()


def _status_by_id(inventory: DependencyInventory) -> dict[str, DependencyStatus]:
    return {
        status.id: status
        for status in (inventory.ffmpeg, inventory.ffprobe, *inventory.python, inventory.whisper_model)
    }


def execute_install_plan(
    plan: InstallPlan,
    *,
    approved_plan_id: str,
    cancellation: Event | None = None,
    progress_callback: Callable[[InstallProgress], None] | None = None,
    cache_dir: Path | None = None,
) -> tuple[InstallResult, ...]:
    """Execute an approved plan serially and verify every installed component."""
    calculated_plan_id = _plan_id(plan.actions)
    if plan.id != calculated_plan_id or approved_plan_id != calculated_plan_id:
        raise DependencyConsentError("The exact dependency install plan was not approved")
    cancellation = cancellation or Event()
    results: list[InstallResult] = []
    for action in plan.actions:
        if cancellation.is_set():
            raise DependencyInstallError("Dependency installation was cancelled")
        _emit(progress_callback, InstallProgress(action.id, "starting", action.description))
        output = _run_action(action, cancellation, progress_callback)
        _emit(progress_callback, InstallProgress(action.id, "verifying", "Verifying installation"))
        statuses = _status_by_id(
            inspect_dependencies(
                cache_dir,
                whisper_library=plan.whisper_library,
                whisper_model=plan.whisper_model,
            )
        )
        failures = [
            statuses[dependency_id]
            for dependency_id in action.dependency_ids
            if not statuses[dependency_id].ready
        ]
        if failures:
            detail = "; ".join(f"{status.name}: {status.detail}" for status in failures)
            raise DependencyInstallError(f"{action.description} did not verify successfully: {detail}")
        result = InstallResult(action.id, action.dependency_ids, output or "Verified")
        results.append(result)
        _emit(progress_callback, InstallProgress(action.id, "completed", "Installation verified"))
    return tuple(results)


def _executable_version(executable: str) -> tuple[str | None, str]:
    try:
        result = subprocess.run(
            [executable, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except OSError as exc:
        return None, str(exc)
    output = (result.stdout or result.stderr).strip()
    first_line = output.splitlines()[0] if output else "no version output"
    if result.returncode != 0:
        return None, first_line
    fields = first_line.split()
    version = fields[2] if len(fields) >= 3 and fields[1] == "version" else None
    return version, first_line


def inspect_executable(
    dependency_id: str,
    name: str,
    executable: str | None,
    required_version: str | None = None,
) -> DependencyStatus:
    if not executable:
        return DependencyStatus(
            id=dependency_id,
            name=name,
            state="missing",
            required_version=required_version,
            installed_version=None,
            path=None,
            detail=f"{name} was not found",
            install_supported=True,
        )
    version, detail = _executable_version(executable)
    version_supported = bool(version and _version_is_supported(version, required_version))
    if version and not version_supported:
        detail = f"installed {version}; requires {required_version}"
    return DependencyStatus(
        id=dependency_id,
        name=name,
        state="ready" if version_supported else "invalid",
        required_version=required_version,
        installed_version=version,
        path=Path(executable),
        detail=detail,
        install_supported=True,
    )


def _version_is_supported(version: str, required_version: str | None) -> bool:
    """Accept every FFmpeg release at or newer than the supported baseline."""
    if required_version != FFMPEG_VERSION:
        return required_version is None or version.startswith(required_version)
    parts = version.split("-", 1)[0].split(".")
    try:
        parsed = tuple(int(part) for part in parts[:2])
    except ValueError:
        return False
    return parsed >= FFMPEG_MINIMUM_VERSION


def inspect_python_dependencies(
    whisper_library: str = "faster-whisper",
) -> tuple[DependencyStatus, ...]:
    statuses: list[DependencyStatus] = []
    for distribution, required_version in _python_dependencies_for_library(whisper_library):
        try:
            installed_version = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            installed_version = None
        state: DependencyState
        if installed_version is None:
            state = "missing"
            detail = f"{distribution} is not installed"
        elif installed_version != required_version:
            state = "invalid"
            detail = f"installed {installed_version}; required {required_version}"
        else:
            state = "ready"
            detail = f"installed {installed_version}"
        statuses.append(
            DependencyStatus(
                id=f"python:{distribution}",
                name=distribution,
                state=state,
                required_version=required_version,
                installed_version=installed_version,
                path=None,
                detail=detail,
                install_supported=True,
            )
        )
    return tuple(statuses)


def inspect_whisper_model(
    cache_dir: Path | None = None,
    *,
    library: str = "faster-whisper",
    model: str = "large-v3",
) -> DependencyStatus:
    """Verify the selected model without network access."""
    cache_dir = (cache_dir or get_whisper_cache_dir()).resolve()
    dependency_id = _whisper_dependency_id(library, model)
    display_name = f"Whisper {model} model ({library})"
    if library == "openai-whisper":
        python_failures = [
            status
            for status in inspect_python_dependencies("openai-whisper")
            if not status.ready
        ]
        if python_failures:
            issues = "; ".join(f"{status.name}: {status.detail}" for status in python_failures)
            return DependencyStatus(
                id=dependency_id,
                name=display_name,
                state="invalid",
                required_version=None,
                installed_version=None,
                path=None,
                detail=(
                    "OpenAI Whisper Python dependencies are not ready. "
                    f"{issues}. Install Python dependencies from setup, then retry model download."
                ),
                install_supported=True,
            )
        try:
            whisper_module = importlib.import_module("whisper")
            model_url = whisper_module._MODELS[model]
            expected_hash = model_url.split("/")[-2]
            model_path = cache_dir / Path(model_url).name
        except (ImportError, KeyError, AttributeError) as exc:
            return DependencyStatus(
                id=dependency_id,
                name=display_name,
                state="missing",
                required_version=None,
                installed_version=None,
                path=None,
                detail=f"OpenAI Whisper or its model definition is unavailable: {exc}",
                install_supported=True,
            )
        if not model_path.is_file() or model_path.stat().st_size == 0:
            return DependencyStatus(
                id=dependency_id,
                name=display_name,
                state="missing",
                required_version=expected_hash,
                installed_version=None,
                path=None,
                detail="model is not cached",
                install_supported=True,
            )
        return DependencyStatus(
            id=dependency_id,
            name=display_name,
            state="ready",
            required_version=expected_hash,
            installed_version=expected_hash,
            path=model_path,
            detail="model file is cached",
            install_supported=True,
        )

    revision = WHISPER_MODEL_REVISION if model == "large-v3" else None
    try:
        from faster_whisper.utils import download_model

        size_or_id = WHISPER_MODEL_ID if model == "large-v3" else model
        model_path = Path(
            download_model(
                size_or_id,
                cache_dir=str(cache_dir),
                local_files_only=True,
                revision=revision,
            )
        )
    except Exception as exc:
        return DependencyStatus(
            id=dependency_id,
            name=display_name,
            state="missing",
            required_version=revision,
            installed_version=None,
            path=None,
            detail=f"pinned model is not cached: {exc}",
            install_supported=True,
        )

    missing_files = tuple(name for name in WHISPER_MODEL_FILES if not (model_path / name).is_file())
    if missing_files:
        return DependencyStatus(
            id=dependency_id,
            name=display_name,
            state="invalid",
            required_version=revision,
            installed_version=None,
            path=model_path,
            detail=f"model cache is incomplete: {', '.join(missing_files)}",
            install_supported=True,
        )
    return DependencyStatus(
        id=dependency_id,
        name=display_name,
        state="ready",
        required_version=revision,
        installed_version=revision,
        path=model_path,
        detail="pinned model files are cached",
        install_supported=True,
    )


def inspect_dependencies(
    cache_dir: Path | None = None,
    *,
    ffmpeg_bin: str | Path | None = None,
    ffprobe_bin: str | Path | None = None,
    whisper_library: str = "faster-whisper",
    whisper_model: str = "large-v3",
) -> DependencyInventory:
    """Return dependency state without installing or downloading anything."""
    return DependencyInventory(
        ffmpeg=inspect_executable(
            "ffmpeg",
            "FFmpeg",
            str(ffmpeg_bin) if ffmpeg_bin else find_ffmpeg(),
            FFMPEG_VERSION,
        ),
        ffprobe=inspect_executable(
            "ffprobe",
            "FFprobe",
            str(ffprobe_bin) if ffprobe_bin else find_ffprobe(),
            FFMPEG_VERSION,
        ),
        python=inspect_python_dependencies(whisper_library),
        whisper_model=inspect_whisper_model(
            cache_dir,
            library=whisper_library,
            model=whisper_model,
        ),
    )


def require_whisper_model_path(
    cache_dir: Path | None = None,
    *,
    library: str = "faster-whisper",
    model: str = "large-v3",
) -> Path:
    """Return the verified selected model path or fail without network access."""
    status = inspect_whisper_model(cache_dir, library=library, model=model)
    if not status.ready or status.path is None:
        raise DependencyNotReadyError(
            f"Whisper {model} ({library}) is not prepared. Install it from the app setup. "
            f"{status.detail}"
        )
    return status.path
