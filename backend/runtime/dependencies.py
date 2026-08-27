"""Structured dependency inventory for application setup workflows."""

from __future__ import annotations

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
    get_directory_size,
    get_whisper_cache_dir,
)


DependencyState = Literal["ready", "missing", "invalid"]
InstallKind = Literal["command", "model_download"]

FFMPEG_WINGET_PACKAGE_ID = "Gyan.FFmpeg.Shared"
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
PYTHON_DEPENDENCIES = (
    ("faster-whisper", "1.2.1"),
    ("better-profanity", "0.7.0"),
    ("numpy", "2.5.2"),
    ("ctranslate2", "4.8.1"),
    ("av", "18.1.0"),
    ("huggingface-hub", "1.28.0"),
)
PYTHON_REQUIREMENTS = tuple(f"{name}=={version}" for name, version in PYTHON_DEPENDENCIES)


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


def find_winget() -> str | None:
    """Find winget, including its Windows application alias."""
    winget = shutil.which("winget")
    if winget:
        return winget
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if not local_app_data:
        return None
    alias = Path(local_app_data) / "Microsoft" / "WindowsApps" / "winget.exe"
    return str(alias) if alias.is_file() else None


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
    platform_name: str | None = None,
    winget: str | None = None,
) -> InstallPlan:
    """Build an inspectable plan without running commands or using the network."""
    requested = tuple(dict.fromkeys(components))
    unknown = sorted(set(requested) - {"ffmpeg", "python", "whisper_model"})
    if unknown:
        raise DependencyPlanError(f"Unknown dependency component(s): {', '.join(unknown)}")

    python_executable = (python_executable or Path(sys.executable)).resolve()
    cache_dir = (cache_dir or get_whisper_cache_dir()).resolve()
    platform_name = platform_name or platform.system()
    actions: list[InstallAction] = []

    if "ffmpeg" in requested:
        if platform_name != "Windows":
            raise DependencyPlanError("Automatic FFmpeg installation is currently supported on Windows only")
        winget = winget or find_winget()
        if not winget:
            raise DependencyPlanError("winget is required for automatic FFmpeg installation")
        actions.append(
            InstallAction(
                id="install-ffmpeg",
                dependency_ids=("ffmpeg", "ffprobe"),
                kind="command",
                description="Install the approved Gyan FFmpeg shared build with winget",
                source_name="Microsoft WinGet / Gyan FFmpeg",
                source_url="https://github.com/GyanD/codexffmpeg/releases",
                command=(
                    winget,
                    "install",
                    "--id",
                    FFMPEG_WINGET_PACKAGE_ID,
                    "--exact",
                    "--accept-package-agreements",
                    "--accept-source-agreements",
                    "--disable-interactivity",
                ),
            )
        )

    if "python" in requested:
        actions.append(
            InstallAction(
                id="install-python-dependencies",
                dependency_ids=tuple(f"python:{name}" for name, _version in PYTHON_DEPENDENCIES),
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
                    *PYTHON_REQUIREMENTS,
                ),
            )
        )

    if "whisper_model" in requested:
        actions.append(
            InstallAction(
                id="download-whisper-large-v3",
                dependency_ids=("whisper:large-v3",),
                kind="model_download",
                description="Download the pinned faster-whisper large-v3 model",
                source_name="Hugging Face / Systran",
                source_url=f"https://huggingface.co/{WHISPER_MODEL_ID}/tree/{WHISPER_MODEL_REVISION}",
                command=(
                    str(python_executable),
                    "-m",
                    "scripts.download_whisper_model",
                    "--cache-dir",
                    str(cache_dir),
                ),
                estimated_download_bytes=WHISPER_MODEL_SIZE_BYTES,
                progress_path=cache_dir,
            )
        )

    action_tuple = tuple(actions)
    if not action_tuple:
        raise DependencyPlanError("At least one dependency component is required")
    return InstallPlan(id=_plan_id(action_tuple), actions=action_tuple)


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
                        "Operation is still running",
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
        statuses = _status_by_id(inspect_dependencies(cache_dir))
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


def inspect_python_dependencies() -> tuple[DependencyStatus, ...]:
    statuses: list[DependencyStatus] = []
    for distribution, required_version in PYTHON_DEPENDENCIES:
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


def inspect_whisper_model(cache_dir: Path | None = None) -> DependencyStatus:
    """Verify the pinned model through faster-whisper without network access."""
    cache_dir = (cache_dir or get_whisper_cache_dir()).resolve()
    try:
        from faster_whisper.utils import download_model

        model_path = Path(
            download_model(
                WHISPER_MODEL_ID,
                cache_dir=str(cache_dir),
                local_files_only=True,
                revision=WHISPER_MODEL_REVISION,
            )
        )
    except Exception as exc:
        return DependencyStatus(
            id="whisper:large-v3",
            name="Whisper large-v3 model",
            state="missing",
            required_version=WHISPER_MODEL_REVISION,
            installed_version=None,
            path=None,
            detail=f"pinned model is not cached: {exc}",
            install_supported=True,
        )

    missing_files = tuple(name for name in WHISPER_MODEL_FILES if not (model_path / name).is_file())
    if missing_files:
        return DependencyStatus(
            id="whisper:large-v3",
            name="Whisper large-v3 model",
            state="invalid",
            required_version=WHISPER_MODEL_REVISION,
            installed_version=None,
            path=model_path,
            detail=f"model cache is incomplete: {', '.join(missing_files)}",
            install_supported=True,
        )
    return DependencyStatus(
        id="whisper:large-v3",
        name="Whisper large-v3 model",
        state="ready",
        required_version=WHISPER_MODEL_REVISION,
        installed_version=WHISPER_MODEL_REVISION,
        path=model_path,
        detail="pinned model files are cached",
        install_supported=True,
    )


def inspect_dependencies(
    cache_dir: Path | None = None,
    *,
    ffmpeg_bin: str | Path | None = None,
    ffprobe_bin: str | Path | None = None,
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
        python=inspect_python_dependencies(),
        whisper_model=inspect_whisper_model(cache_dir),
    )


def require_whisper_model_path(cache_dir: Path | None = None) -> Path:
    """Return the verified pinned model path or fail without network access."""
    status = inspect_whisper_model(cache_dir)
    if not status.ready or status.path is None:
        raise DependencyNotReadyError(
            "Whisper large-v3 is not prepared. Review and approve a dependency "
            f"download plan first. {status.detail}"
        )
    return status.path
