"""Desktop setup coordination; installation mechanics belong to backend.runtime."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, RLock
from typing import Any
from backend.runtime import (
    FFMPEG_VERSION,
    build_install_plan,
    execute_install_plan,
    get_application_runtime_root,
    get_managed_ffmpeg_paths,
    resolve_whisper_cache_dir,
    inspect_executable,
    inspect_whisper_model,
)
from backend.runtime.dependency_inspection import inspect_ytdlp
from backend.runtime.locations import get_managed_ytdlp_path
from backend.service import BackendService
from backend.runtime.dependency_models import InstallPlan


class InstallationController:
    """Own approved plans, setup workers, and installation status snapshots."""

    def __init__(self, service: BackendService):
        self.service = service
        self._install_plans: dict[str, InstallPlan] = {}
        self._install_jobs: dict[str, dict[str, Any]] = {}
        self._install_lock = RLock()
        self._closing = False
        self._install_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="desktop-install")


    def _serialize_install_state(self, install_id: str) -> dict[str, Any]:
        with self._install_lock:
            state = self._install_jobs[install_id]
            return {
                "install_id": install_id,
                "status": state["status"],
                "action_id": state.get("action_id"),
                "action_index": state.get("action_index"),
                "action_count": state.get("action_count"),
                "phase": state.get("phase"),
                "message": state.get("message"),
                "completed_bytes": state.get("completed_bytes"),
                "total_bytes": state.get("total_bytes"),
                "started_at": state.get("started_at"),
                "error": state.get("error"),
            }

    def _run_install_task(self, install_id: str, plan_id: str, plan: InstallPlan, cache_dir: Path | None) -> None:
        with self._install_lock:
            cancellation = self._install_jobs[install_id]["cancel_event"]
        try:
            def callback(progress: object) -> None:
                action_index = next(
                    (index + 1 for index, action in enumerate(plan.actions) if action.id == progress.action_id),
                    None,
                )
                with self._install_lock:
                    state = self._install_jobs[install_id]
                    # A completed component is not a completed plan. Keep polling
                    # until all components verify and settings have been saved.
                    state["status"] = "canceling" if cancellation.is_set() else "running"
                    state["action_id"] = progress.action_id
                    state["phase"] = progress.phase
                    state["message"] = progress.message
                    state["completed_bytes"] = progress.completed_bytes
                    state["total_bytes"] = progress.total_bytes
                    state["action_index"] = action_index if action_index is not None else state.get("action_index")
                    state["action_count"] = len(plan.actions)
                    if progress.phase == "completed":
                        state["message"] = "Installation verified"
                    if progress.phase == "cancelled":
                        state["error"] = "The installation was cancelled"

            results = execute_install_plan(
                plan,
                approved_plan_id=plan_id,
                cancellation=cancellation,
                progress_callback=callback,
                cache_dir=cache_dir,
            )
            installed_ids = {
                dependency_id
                for result in results
                for dependency_id in result.dependency_ids
            }
            settings = self.service.get_settings()
            runtime = dict(settings["runtime"])
            runtime_root = get_application_runtime_root()
            if {"ffmpeg", "ffprobe"}.issubset(installed_ids):
                ffmpeg_path, ffprobe_path = get_managed_ffmpeg_paths(runtime_root)
                if not ffmpeg_path or not ffprobe_path:
                    raise RuntimeError("Managed FFmpeg completed but its verified paths are unavailable")
                runtime["ffmpeg_path"] = ffmpeg_path
                runtime["ffprobe_path"] = ffprobe_path
            if any(dependency_id.startswith("whisper:") for dependency_id in installed_ids):
                runtime["whisper_cache"] = str(cache_dir)
            if "ytdlp" in installed_ids:
                ytdlp_path = get_managed_ytdlp_path(runtime_root)
                if not ytdlp_path.is_file():
                    raise RuntimeError("Managed yt-dlp completed but its verified path is unavailable")
                runtime["ytdlp_path"] = str(ytdlp_path)
            if runtime != settings["runtime"]:
                settings["runtime"] = runtime
                self.service.update_settings(settings)

            with self._install_lock:
                state = self._install_jobs[install_id]
                state["status"] = "completed"
                state["phase"] = "completed"
                state["message"] = "Installation complete and verified"
                state["error"] = None
                state["completed_bytes"] = None
                state["total_bytes"] = None
                state["action_id"] = results[-1].action_id if results else state.get("action_id")
                state["action_index"] = len(plan.actions) if results else state.get("action_index")
        except Exception as exc:
            with self._install_lock:
                state = self._install_jobs[install_id]
                state["status"] = "cancelled" if cancellation.is_set() else "failed"
                if cancellation.is_set():
                    state["phase"] = "cancelled"
                state["message"] = "Installation failed"
                state["error"] = str(exc)

    def _cancel_install(self, install_id: str) -> dict[str, Any]:
        with self._install_lock:
            state = self._install_jobs[install_id]
            # A late cancel request must not revive an already settled install.
            if state["status"] not in {"completed", "failed", "cancelled"}:
                state["cancel_event"].set()
                state["status"] = "canceling"
                state["message"] = "Cancelling installation"
        return self._serialize_install_state(install_id)

    def handle(self, method: str, params: Mapping[str, Any] | None = None) -> object:
        params = params or {}
        if method == "dependencies.plan":
            runtime_root = get_application_runtime_root()
            cache_dir = resolve_whisper_cache_dir(self.service.settings.runtime.whisper_cache)
            plan = build_install_plan(
                list(params["components"]),
                cache_dir=cache_dir,
                runtime_root=runtime_root,
                whisper_library=self.service.settings.whisper.library,
                whisper_model=self.service.settings.whisper.model,
            )
            self._install_plans[plan.id] = plan
            return {
                "plan_id": plan.id,
                "actions": [
                    {
                        "id": action.id,
                        "dependencies": action.dependency_ids,
                        "description": action.description,
                        "source_name": action.source_name,
                        "source_url": action.source_url,
                        "command": action.command,
                        "estimated_download_bytes": action.estimated_download_bytes,
                        "component": action.component,
                        "version": action.version,
                        "purpose": action.purpose,
                        "license": action.license,
                        "requires_network": action.requires_network,
                        "destination": str(action.destination),
                    }
                    for action in plan.actions
                ],
            }
        if method == "dependencies.install":
            with self._install_lock:
                if self._closing:
                    raise RuntimeError("The local processing service is closing")
                plan_id = params["plan_id"]
                plan = self._install_plans.get(plan_id)
                if plan is None:
                    raise ValueError("Dependency plan is unknown or expired; review it again")
                install_id = uuid.uuid4().hex
                started_at = datetime.now(timezone.utc).isoformat()
                state = {
                    "status": "running",
                    "action_id": None,
                    "action_index": 0,
                    "action_count": len(plan.actions),
                    "phase": "starting",
                    "message": "Preparing required components",
                    "completed_bytes": None,
                    "total_bytes": None,
                    "started_at": started_at,
                    "error": None,
                    "plan_id": plan_id,
                    "plan": plan,
                    # Allocate before scheduling so an immediate cancellation is retained.
                    "cancel_event": Event(),
                }
                self._install_jobs[install_id] = state
                snapshot = self._serialize_install_state(install_id)
                self._install_executor.submit(
                    self._run_install_task,
                    install_id,
                    plan_id,
                    plan,
                    resolve_whisper_cache_dir(self.service.settings.runtime.whisper_cache),
                )
                return snapshot
        if method == "dependencies.status":
            install_id = params["install_id"]
            if install_id not in self._install_jobs:
                raise ValueError("Dependency install is unknown or expired")
            return self._serialize_install_state(install_id)
        if method == "dependencies.cancel":
            install_id = params["install_id"]
            if install_id not in self._install_jobs:
                raise ValueError("Dependency install is unknown or expired")
            return self._cancel_install(install_id)
        if method == "dependencies.inspect_ffmpeg":
            return self._inspect_ffmpeg_selection(params.get("path"))
        if method == "dependencies.locate_ffmpeg":
            selected = self._inspect_ffmpeg_selection(params.get("path"))
            settings = self.service.get_settings()
            runtime = dict(settings["runtime"])
            runtime["ffmpeg_path"] = selected["ffmpeg_path"]
            runtime["ffprobe_path"] = selected["ffprobe_path"]
            settings["runtime"] = runtime
            self.service.update_settings(settings)
            return self.service.get_capabilities()
        if method == "dependencies.locate_model":
            selected = params.get("path")
            if not isinstance(selected, str) or not selected.strip():
                raise ValueError("Choosing an existing Whisper model requires a cache directory")
            cache_dir = Path(selected).expanduser().resolve()
            status = inspect_whisper_model(
                cache_dir,
                library=self.service.settings.whisper.library,
                model=self.service.settings.whisper.model,
            )
            if not status.ready:
                raise ValueError(f"The selected model cache is not ready: {status.detail}")
            settings = self.service.get_settings()
            runtime = dict(settings["runtime"])
            runtime["whisper_cache"] = str(cache_dir)
            settings["runtime"] = runtime
            self.service.update_settings(settings)
            return self.service.get_capabilities()
        if method == "dependencies.locate_ytdlp":
            selected = params.get("path")
            if not isinstance(selected, str) or not selected.strip():
                raise ValueError("Choosing yt-dlp requires an executable path")
            status = inspect_ytdlp(str(Path(selected).expanduser().resolve()))
            if not status.ready or not status.path:
                raise ValueError(f"The selected yt-dlp executable is not ready: {status.detail}")
            settings = self.service.get_settings()
            runtime = dict(settings["runtime"])
            runtime["ytdlp_path"] = str(status.path)
            settings["runtime"] = runtime
            self.service.update_settings(settings)
            return self.service.get_capabilities()
        raise ValueError(f"Unknown desktop bridge method: {method}")

    @staticmethod
    def _inspect_ffmpeg_selection(selected: object) -> dict[str, object]:
        if not isinstance(selected, str) or not selected.strip():
            raise ValueError("Choosing FFmpeg requires an executable path")
        ffmpeg_path = Path(selected).expanduser().resolve()
        if ffmpeg_path.name.lower() not in {"ffmpeg", "ffmpeg.exe"}:
            raise ValueError("Select ffmpeg.exe (or ffmpeg on non-Windows systems)")
        companion_name = "ffprobe.exe" if ffmpeg_path.suffix.lower() == ".exe" else "ffprobe"
        ffprobe_path = ffmpeg_path.with_name(companion_name)
        ffmpeg = inspect_executable("ffmpeg", "FFmpeg", str(ffmpeg_path), FFMPEG_VERSION)
        ffprobe = inspect_executable("ffprobe", "FFprobe", str(ffprobe_path), FFMPEG_VERSION)
        failures = [status for status in (ffmpeg, ffprobe) if not status.ready]
        if failures:
            detail = "; ".join(f"{status.name}: {status.detail}" for status in failures)
            raise ValueError(f"The selected FFmpeg installation is not ready: {detail}")
        return {
            "ffmpeg_path": str(ffmpeg_path),
            "ffprobe_path": str(ffprobe_path),
            "version": ffmpeg.installed_version,
        }

    def cancel_pending(self) -> None:
        # Signal setup before the service waits for any media workers to finish.
        with self._install_lock:
            self._closing = True
            for state in self._install_jobs.values():
                state["cancel_event"].set()

    def close(self) -> None:
        self._install_executor.shutdown(wait=True, cancel_futures=True)
