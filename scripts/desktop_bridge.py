#!/usr/bin/env python3
"""Expose BackendService to Electron over a private JSON-lines child process."""

from __future__ import annotations

import json
import math
import sys
import uuid
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Lock
from typing import Any, TextIO

from backend.policy import PolicyStore, ProfanityPolicy
from backend.runtime import (
    FFMPEG_VERSION,
    build_install_plan,
    execute_install_plan,
    get_application_runtime_root,
    get_managed_ffmpeg_directory,
    get_managed_ffmpeg_paths,
    get_managed_whisper_cache_dir,
    inspect_executable,
    inspect_whisper_model,
)
from backend.censor import find_review_candidates
from backend.jobs.media import transcript_path
from backend.service import BackendService


class DesktopBridge:
    def __init__(
        self,
        service: BackendService | None = None,
        policy_store: PolicyStore | None = None,
    ):
        self.service = service or BackendService()
        self.policy_store = policy_store or PolicyStore()
        self._install_plans = {}
        self._install_jobs = {}
        self._install_lock = Lock()
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

    def _run_install_task(self, install_id: str, plan_id: str, plan: object, cache_dir: Path | None) -> None:
        cancellation = Event()
        with self._install_lock:
            self._install_jobs[install_id]["cancel_event"] = cancellation
        try:
            def callback(progress: object) -> None:
                action_index = next(
                    (index + 1 for index, action in enumerate(plan.actions) if action.id == progress.action_id),
                    None,
                )
                with self._install_lock:
                    state = self._install_jobs[install_id]
                    state["status"] = (
                        "completed" if progress.phase == "completed"
                        else "cancelled" if progress.phase == "cancelled"
                        else "running"
                    )
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
                state["status"] = "failed"
                if cancellation.is_set():
                    state["phase"] = "cancelled"
                state["message"] = "Installation failed"
                state["error"] = str(exc)

    def _cancel_install(self, install_id: str) -> dict[str, Any]:
        with self._install_lock:
            state = self._install_jobs[install_id]
            cancel_event = state.get("cancel_event")
            if cancel_event is not None:
                cancel_event.set()
            state["status"] = "canceling"
            state["message"] = "Cancelling installation"
        return self._serialize_install_state(install_id)

    def handle(self, method: str, params: Mapping[str, Any] | None = None) -> object:
        params = params or {}
        if method == "settings.get":
            return self.service.get_settings()
        if method == "settings.update":
            return self.service.update_settings(params["settings"])
        if method == "capabilities.get":
            return self.service.get_capabilities()
        if method == "dictionary.info":
            return self.policy_store.info()
        if method == "dictionary.exclusions":
            return self._dictionary_entries("exclude", params)
        if method == "dictionary.censored":
            return self._dictionary_entries("censor", params)
        if method == "dictionary.discovered":
            self.policy_store.initialize_discovered()
            return {"words": list(self.policy_store.load_discovered())}
        if method == "dictionary.add":
            target = params.get("target")
            word = params.get("word")
            if target not in ("censor", "exclude") or not isinstance(word, str):
                raise ValueError("Dictionary updates require a censor/exclude target and a word")
            policy, changed = self.policy_store.update(target, word, "add")
            result = self._dictionary_result(policy)
            result["changed"] = changed
            return result
        if method == "dictionary.remove":
            target = params.get("target")
            word = params.get("word")
            if target not in ("censor", "exclude") or not isinstance(word, str):
                raise ValueError("Dictionary updates require a censor/exclude target and a word")
            policy, changed = self.policy_store.update(target, word, "remove")
            result = self._dictionary_result(policy)
            result["changed"] = changed
            return result
        if method == "dictionary.restore_defaults":
            return self._dictionary_result(self.policy_store.restore_defaults())
        if method == "dictionary.import":
            source = params.get("source")
            if not isinstance(source, str) or not source.strip():
                raise ValueError("Dictionary import requires a source file")
            return self._dictionary_result(self.policy_store.import_dictionary(Path(source)))
        if method == "dictionary.export":
            destination = params.get("destination")
            if not isinstance(destination, str) or not destination.strip():
                raise ValueError("Dictionary export requires a destination file")
            exported = self.policy_store.export_dictionary(Path(destination))
            return {"path": str(exported)}
        if method == "reviews.list":
            source = Path(params["source"]).expanduser().resolve()
            transcript = transcript_path(source, self.service.settings.directories.transcripts)
            if not transcript.is_file():
                raise ValueError("No transcript is available for this file. Run Report only first.")
            try:
                words_data = json.loads(transcript.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Transcript could not be read: {transcript}") from exc
            policy = self.policy_store.load()
            candidates = find_review_candidates(
                words_data,
                set(policy.censor_words),
                set(policy.exclusions),
            )
            censored = []
            for word_obj in words_data.get("words", []):
                word = str(word_obj.get("word", "")).strip(".,!?;:\"' \t")
                if word and word.lower() in policy.censor_words and word.lower() not in policy.exclusions:
                    censored.append({
                        "word": word.lower(),
                        "start": word_obj.get("start"),
                        "end": word_obj.get("end"),
                    })
            self.policy_store.add_discovered({candidate["word"] for candidate in candidates})
            return {"source": str(source), "candidates": candidates, "censored": censored}
        if method == "dependencies.plan":
            runtime_root = get_application_runtime_root()
            cache_dir = (
                self.service.settings.runtime.whisper_cache
                or get_managed_whisper_cache_dir(runtime_root)
            )
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
                        "destination": self._install_destination(
                            action.id,
                            runtime_root,
                            cache_dir,
                        ),
                    }
                    for action in plan.actions
                ],
            }
        if method == "dependencies.install":
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
                "cancel_event": None,
            }
            self._install_jobs[install_id] = state
            snapshot = self._serialize_install_state(install_id)
            self._install_executor.submit(
                self._run_install_task,
                install_id,
                plan_id,
                plan,
                (
                    self.service.settings.runtime.whisper_cache
                    or get_managed_whisper_cache_dir(get_application_runtime_root())
                ),
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
        if method == "library.list":
            return [item.to_dict() for item in self.service.get_library()]
        if method == "library.archive":
            return self.service.archive_source(Path(params["source"]))
        if method == "library.import":
            sources = params.get("sources")
            if not isinstance(sources, list) or not all(isinstance(source, str) for source in sources):
                raise ValueError("Adding files requires a list of file paths")
            return self.service.import_sources([Path(source) for source in sources])
        if method == "archive.list":
            return [item.to_dict() for item in self.service.get_archive()]
        if method == "archive.restore":
            source = params.get("source")
            if not isinstance(source, str):
                raise ValueError("Returning an archived file requires a file path")
            return self.service.restore_archive_source(Path(source))
        if method == "archive.purge":
            source = params.get("source")
            if source is None:
                return self.service.purge_archive()
            if not isinstance(source, str):
                raise ValueError("Archive deletion requires a file path")
            return self.service.purge_archive_source(Path(source))
        if method == "jobs.list":
            return [job.to_dict() for job in self.service.jobs.list()]
        if method == "jobs.submit":
            mode = params.get("mode")
            source = params.get("source")
            force_transcribe = params.get("force_transcribe", False)
            overwrite_output = params.get("overwrite_output", False)
            if (
                not isinstance(source, str)
                or mode not in ("copy", "report_only", "censor")
                or not isinstance(force_transcribe, bool)
                or not isinstance(overwrite_output, bool)
            ):
                raise ValueError("Job submission requires a source and supported mode")
            job = self.service.submit_job(
                Path(source),
                mode,
                force_transcribe=force_transcribe,
                overwrite_output=overwrite_output,
            )
            return job.to_dict()
        if method == "jobs.submit_many":
            mode = params.get("mode")
            sources = params.get("sources")
            if (
                mode not in ("copy", "report_only", "censor")
                or not isinstance(sources, list)
                or not all(isinstance(source, str) for source in sources)
            ):
                raise ValueError("Batch submission requires source paths and a supported mode")
            return [
                result.to_dict()
                for result in self.service.submit_jobs(
                    [Path(source) for source in sources],
                    mode,
                )
            ]
        if method == "jobs.get":
            return self.service.jobs.get(params["job_id"]).to_dict()
        if method == "jobs.events":
            events = self.service.jobs.events(
                params["job_id"],
                int(params.get("after_sequence", 0)),
            )
            return [event.to_dict() for event in events]
        if method == "jobs.cancel":
            return self.service.jobs.cancel(params["job_id"]).to_dict()
        raise ValueError(f"Unknown desktop bridge method: {method}")

    def close(self) -> None:
        self.service.close()

    @staticmethod
    def _dictionary_result(policy: ProfanityPolicy) -> dict[str, object]:
        return {
            "dictionary_path": str(policy.dictionary_path),
            "schema_version": policy.schema_version,
            "seeded_from_default_version": policy.seeded_from_default_version,
            "words_count": len(policy.censor_words),
            "exclusions_count": len(policy.exclusions),
        }

    def _dictionary_entries(
        self,
        target: str,
        params: Mapping[str, Any],
    ) -> dict[str, object]:
        page = params.get("page", 1)
        page_size = params.get("page_size", 25)
        sort = params.get("sort", "value")
        direction = params.get("direction", "asc")
        search = params.get("search", "")
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise ValueError("Dictionary page must be a positive integer")
        if isinstance(page_size, bool) or not isinstance(page_size, int) or not 10 <= page_size <= 100:
            raise ValueError("Dictionary page size must be between 10 and 100")
        if sort not in ("value", "added_at", "source") or direction not in ("asc", "desc"):
            raise ValueError("Dictionary sort is not supported")
        if not isinstance(search, str):
            raise ValueError("Dictionary search must be text")

        entries = list(self.policy_store.load_entries(target))
        normalized_search = search.strip().lower()
        if normalized_search:
            entries = [entry for entry in entries if normalized_search in entry.value]
        entries.sort(
            key=lambda entry: (getattr(entry, sort), entry.value),
            reverse=direction == "desc",
        )
        total = len(entries)
        start = (page - 1) * page_size
        return {
            "target": target,
            "items": [asdict(entry) for entry in entries[start:start + page_size]],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": math.ceil(total / page_size),
        }

    @staticmethod
    def _install_destination(action_id: str, runtime_root: Path, cache_dir: Path) -> str:
        if "ffmpeg" in action_id:
            return str(get_managed_ffmpeg_directory(runtime_root))
        if action_id.startswith("download-"):
            return str(cache_dir)
        return "The repository-local Python environment"

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

def serve(
    bridge: DesktopBridge | None = None,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> int:
    bridge = bridge or DesktopBridge()
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    output_lock = Lock()

    def dispatch(line: str) -> None:
        request_id: object = None
        try:
            request = json.loads(line)
            request_id = request.get("id")
            result = bridge.handle(request["method"], request.get("params"))
            response = {"id": request_id, "ok": True, "result": result}
        except Exception as exc:
            response = {
                "id": request_id,
                "ok": False,
                "error": {"type": type(exc).__name__, "message": str(exc)},
            }
        with output_lock:
            output_stream.write(json.dumps(response, separators=(",", ":")) + "\n")
            output_stream.flush()

    try:
        with ThreadPoolExecutor(max_workers=4, thread_name_prefix="desktop-bridge") as executor:
            for line in input_stream:
                if line.strip():
                    executor.submit(dispatch, line)
    finally:
        bridge.close()
    return 0


def main() -> int:
    protocol_output = sys.stdout
    sys.stdout = sys.stderr
    return serve(output_stream=protocol_output)


if __name__ == "__main__":
    raise SystemExit(main())
