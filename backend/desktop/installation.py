"""Desktop setup coordination; installation mechanics belong to backend.runtime."""

from __future__ import annotations

import uuid
import json
from dataclasses import dataclass, replace
from copy import deepcopy
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
from backend.runtime.locations import get_managed_ytdlp_path, get_managed_ffmpeg_directory
from backend.service import BackendService, ServiceBusyError
from backend.runtime.dependency_models import InstallPlan


@dataclass(frozen=True)
class VerificationContext:
    baseline_json: str
    runtime_root: Path
    cache_dir: Path
    library: str
    model: str

    @property
    def baseline(self):
        return json.loads(self.baseline_json)


class InstallationController:
    """Own approved plans, setup workers, and installation status snapshots."""

    def __init__(self, service: BackendService):
        self.service = service
        self._install_plans: dict[str, InstallPlan] = {}
        self._plan_contexts: dict[str, VerificationContext] = {}
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
                "resolution": deepcopy(state.get("resolution")),
                "verified_values": {f"runtime.{key}": value for key, value in state.get("values", {}).items()},
            }

    def _run_install_task(self, install_id: str, plan_id: str, plan: InstallPlan, cache_dir: Path | None) -> None:
        with self._install_lock:
            cancellation = self._install_jobs[install_id]["cancel_event"]
        try:
            completed_ids: set[str] = set()
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
                        completed_ids.update(dependency_id for action in plan.actions if action.id == progress.action_id
                                             for dependency_id in action.dependency_ids)
                    if progress.phase == "cancelled":
                        state["error"] = "The installation was cancelled"

            try:
                results = execute_install_plan(
                    plan,
                    approved_plan_id=plan_id,
                    cancellation=cancellation,
                    progress_callback=callback,
                    cache_dir=cache_dir,
                )
                completed_ids.update(dependency_id for result in results for dependency_id in result.dependency_ids)
            except Exception as exc:
                if not completed_ids:
                    raise
                self._install_jobs[install_id]["install_error"] = str(exc)
            installed_ids = completed_ids
            context = self._install_jobs[install_id]["context"]
            values = {}
            if {"ffmpeg", "ffprobe"}.issubset(installed_ids):
                ffmpeg_path, ffprobe_path = get_managed_ffmpeg_paths(context.runtime_root)
                if not ffmpeg_path or not ffprobe_path:
                    raise RuntimeError("Managed FFmpeg completed but its verified paths are unavailable")
                for candidate in (ffmpeg_path, ffprobe_path):
                    Path(candidate).resolve().relative_to(get_managed_ffmpeg_directory(context.runtime_root))
                values.update(ffmpeg_path=ffmpeg_path, ffprobe_path=ffprobe_path)
            if any(dependency_id.startswith("whisper:") for dependency_id in installed_ids):
                values["whisper_cache"] = str(context.cache_dir)
            if "ytdlp" in installed_ids:
                values["ytdlp_path"] = str(get_managed_ytdlp_path(context.runtime_root))
            with self._install_lock:
                self._install_jobs[install_id]["values"] = values
            self._apply_verified(install_id, context.baseline, values)
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
            if state["status"] in {"running", "canceling"}:
                state["cancel_event"].set()
                state["status"] = "canceling"
                state["message"] = "Cancelling installation"
        return self._serialize_install_state(install_id)

    def handle(self, method: str, params: Mapping[str, Any] | None = None) -> object:
        params = params or {}
        if method == "dependencies.plan":
            context = self._capture_context()
            plan = build_install_plan(
                list(params["components"]),
                cache_dir=context.cache_dir,
                runtime_root=context.runtime_root,
                whisper_library=context.library,
                whisper_model=context.model,
            )
            with self._install_lock:
                # A reviewed plan keeps its original baseline until it has been consumed.
                active = any(state.get("plan_id") == plan.id and state["status"] not in {"failed", "cancelled"}
                             for state in self._install_jobs.values())
                if not active:
                    self._install_plans[plan.id] = plan
                    self._plan_contexts[plan.id] = context
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
                for existing_id, existing in self._install_jobs.items():
                    if existing.get("plan_id") == plan_id and existing["status"] not in {"failed", "cancelled"}:
                        return self._serialize_install_state(existing_id)
                    if existing["status"] in {"running", "canceling", "awaiting_resolution", "resolving"}:
                        components = {action.component for action in plan.actions}
                        if components.intersection(existing.get("components", set())):
                            raise ServiceBusyError("Another setup operation for this component needs attention")
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
                    "components": {action.component for action in plan.actions},
                    "context": self._plan_contexts[plan_id],
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
                    self._plan_contexts[plan_id].cache_dir,
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
        if method == "dependencies.resolve_conflict":
            return self._resolve(params)
        if method in {"dependencies.locate_ffmpeg", "dependencies.locate_model", "dependencies.locate_ytdlp"}:
            context = self._capture_context()
            selected = params.get("path")
            if not isinstance(selected, str) or not selected.strip():
                raise ValueError("Choose an existing component path")
            selected = str(Path(selected).expanduser().resolve())
            if method.endswith("locate_ffmpeg"):
                inspected = self._inspect_ffmpeg_selection(selected)
                values = {key: inspected[key] for key in ("ffmpeg_path", "ffprobe_path")}
            elif method.endswith("locate_model"):
                values = {"whisper_cache": selected}
            else:
                values = {"ytdlp_path": selected}
            self._revalidate(context, values)
            operation_id = uuid.uuid4().hex
            with self._install_lock:
                self._install_jobs[operation_id] = {
                    "status": "running", "context": context, "values": values,
                    "cancel_event": Event(), "message": "Existing component verified",
                }
            self._apply_verified(operation_id, context.baseline, values)
            return self._serialize_install_state(operation_id)
        raise ValueError(f"Unknown desktop bridge method: {method}")

    def _capture_context(self):
        baseline = self.service.get_settings_snapshot()
        settings = baseline["settings"]
        cache = settings["runtime"]["whisper_cache"]
        return VerificationContext(json.dumps(baseline), get_application_runtime_root().resolve(),
                                   resolve_whisper_cache_dir(Path(cache) if cache else None),
                                   settings["whisper"]["library"], settings["whisper"]["model"])

    def _revalidate(self, context, values):
        if "ffmpeg_path" in values:
            pair = self._inspect_ffmpeg_selection(values["ffmpeg_path"])
            if pair["ffprobe_path"] != values["ffprobe_path"]:
                raise ValueError("FFmpeg and FFprobe must belong to the same verified installation")
        if "whisper_cache" in values:
            status = inspect_whisper_model(Path(values["whisper_cache"]), library=context.library, model=context.model)
            if not status.ready:
                raise ValueError(f"The selected model cache is not ready: {status.detail}")
        if "ytdlp_path" in values:
            status = inspect_ytdlp(values["ytdlp_path"])
            if not status.ready:
                raise ValueError(f"The selected yt-dlp executable is not ready: {status.detail}")

    def _apply_verified(self, operation_id, baseline, values, *, strict=False):
        state = self._install_jobs[operation_id]
        try:
            self._revalidate(state["context"], values)
            result = self.service.apply_runtime_changes(baseline, values, strict=strict)
            error = None
        except Exception as exc:
            # Verification, media guards and persistence errors retain the installed assets.
            result = {"status": "conflict", "snapshot": self.service.get_settings_snapshot(), "conflicts": []}
            error = str(exc)
        with self._install_lock:
            state["status"] = "completed" if result["status"] == "saved" else "awaiting_resolution"
            state["phase"] = state["status"]
            state["message"] = "Component settings saved" if state["status"] == "completed" else "Verified components need settings review"
            state["error"] = error
            state["resolution"] = result if state["status"] == "awaiting_resolution" else None
            if state["status"] == "completed" and state.get("install_error"):
                state["status"] = "cancelled" if state["cancel_event"].is_set() else "failed"
                state["error"] = state["install_error"]
            state["completed_bytes"] = None
            state["total_bytes"] = None

    def _resolve(self, params):
        operation_id = params.get("install_id")
        with self._install_lock:
            state = self._install_jobs.get(operation_id)
            if state is None or state["status"] != "awaiting_resolution":
                raise ValueError("This component is not awaiting settings resolution")
            resolution = state["resolution"]
            if params.get("revision") != resolution["snapshot"]["revision"]:
                raise ValueError("Use the latest settings resolution snapshot")
            choices = params.get("choices")
            values = state["values"]
            if not isinstance(choices, dict) or set(choices) != {f"runtime.{key}" for key in values}:
                raise ValueError("Choose keep-current or use-verified for every verified field")
            if any(choice not in {"keep_current", "use_verified"} for choice in choices.values()):
                raise ValueError("Unsupported settings resolution choice")
            if "ffmpeg_path" in values and choices["runtime.ffmpeg_path"] != choices["runtime.ffprobe_path"]:
                raise ValueError("Resolve FFmpeg and FFprobe together")
            selected = {key: value if choices[f"runtime.{key}"] == "use_verified" else resolution["snapshot"]["settings"]["runtime"][key]
                        for key, value in values.items()}
            state["status"] = "resolving"
        try:
            # Recheck original verified assets, even when retaining a manual selection.
            self._revalidate(replace(state["context"], model=resolution["snapshot"]["settings"]["whisper"]["model"]), values)
            self._apply_resolution(operation_id, resolution["snapshot"], selected)
        except Exception as exc:
            with self._install_lock:
                state["status"] = "awaiting_resolution"
                state["error"] = str(exc)
        return self._serialize_install_state(operation_id)

    def _apply_resolution(self, operation_id, baseline, selected):
        # Keep-current may be unready; only use-verified requires the original verification.
        state = self._install_jobs[operation_id]
        try:
            result = self.service.apply_runtime_changes(baseline, selected, strict=True)
            error = None
        except Exception as exc:
            result = {"status": "conflict", "snapshot": self.service.get_settings_snapshot(), "conflicts": []}
            error = str(exc)
        with self._install_lock:
            state["status"] = "completed" if result["status"] == "saved" else "awaiting_resolution"
            state["phase"] = state["status"]
            state["resolution"] = result if state["status"] == "awaiting_resolution" else None
            state["error"] = error
            if state["status"] == "completed" and state.get("install_error"):
                state["status"] = "cancelled" if state["cancel_event"].is_set() else "failed"
                state["error"] = state["install_error"]

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
