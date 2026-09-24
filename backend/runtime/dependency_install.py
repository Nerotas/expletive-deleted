"""Execute approved plans with cancellation and post-install verification."""

from __future__ import annotations

import importlib
import importlib.metadata
import subprocess
import time
from pathlib import Path
from threading import Event
from typing import Callable
from backend.runtime.paths import (
    PROJECT_ROOT,
)
from backend.runtime.locations import (
    get_directory_size,
    get_managed_ffmpeg_paths,
)
from .dependency_inspection import (
    inspect_dependencies,
)
from backend.runtime.dependency_errors import DependencyConsentError, DependencyInstallError
from .dependency_models import (
    DependencyInventory,
    DependencyStatus,
    InstallAction,
    InstallPlan,
    InstallProgress,
    InstallResult,
)
from .dependency_plan import (
    _plan_id,
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
    statuses = {
        status.id: status
        for status in (inventory.ffmpeg, inventory.ffprobe, *inventory.python, inventory.whisper_model)
    }
    statuses[inventory.ytdlp.id] = inventory.ytdlp
    statuses[inventory.js_runtime.id] = inventory.js_runtime
    return statuses


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
        importlib.invalidate_caches()
        _emit(progress_callback, InstallProgress(action.id, "verifying", "Verifying installation"))
        # Verify the approved output, not a runtime override pointing elsewhere.
        verification_paths: dict[str, Path] = {}
        if {"ffmpeg", "ffprobe"}.issubset(action.dependency_ids) and action.destination is not None:
            # The approved runtime destination owns the manifest; ambient overrides
            # must not make a different installation satisfy this verification.
            ffmpeg, ffprobe = get_managed_ffmpeg_paths(action.destination.parent.parent)
            if not ffmpeg or not ffprobe:
                raise DependencyInstallError("The approved FFmpeg/FFprobe destination has no verified pair")
            for candidate in (ffmpeg, ffprobe):
                try:
                    Path(candidate).resolve().relative_to(action.destination.resolve())
                except ValueError as exc:
                    raise DependencyInstallError("FFmpeg verification escaped the approved destination") from exc
            verification_paths.update(ffmpeg_bin=Path(ffmpeg), ffprobe_bin=Path(ffprobe))
        if action.component == "ytdlp" and action.destination is not None:
            verification_paths["ytdlp_bin"] = action.destination / "yt-dlp.exe"
        if action.component == "js_runtime" and action.destination is not None:
            verification_paths["js_runtime_bin"] = action.destination / "deno.exe"
        statuses = _status_by_id(
            inspect_dependencies(
                cache_dir,
                whisper_library=plan.whisper_library,
                whisper_model=plan.whisper_model,
                **verification_paths,
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
