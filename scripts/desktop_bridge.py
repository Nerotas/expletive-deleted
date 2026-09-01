#!/usr/bin/env python3
"""Expose BackendService to Electron over a private JSON-lines child process."""

from __future__ import annotations

import json
import math
import sys
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
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

    def handle(self, method: str, params: Mapping[str, Any] | None = None) -> object:
        params = params or {}
        if method == "settings.get":
            return self.service.get_settings()
        if method == "settings.update":
            return self.service.update_settings(params["settings"])
        if method == "capabilities.get":
            return self.service.get_capabilities()
        if method == "dictionary.get":
            return self._dictionary()
        if method == "dictionary.summary":
            return self._dictionary_summary()
        if method == "dictionary.entries":
            return self._dictionary_entries(params)
        if method == "dictionary.discovered":
            policy = self.policy_store.load()
            return {
                "words": self._discovered_words(
                    set(policy.censor_words),
                    set(policy.exclusions),
                )
            }
        if method == "dictionary.add":
            target = params.get("target")
            word = params.get("word")
            if target not in ("censor", "exclude") or not isinstance(word, str):
                raise ValueError("Dictionary updates require a censor/exclude target and a word")
            policy, changed = self.policy_store.update(target, word, "add")
            result = self._dictionary_summary(policy)
            result["changed"] = changed
            return result
        if method == "dictionary.remove":
            target = params.get("target")
            word = params.get("word")
            if target not in ("censor", "exclude") or not isinstance(word, str):
                raise ValueError("Dictionary updates require a censor/exclude target and a word")
            policy, changed = self.policy_store.update(target, word, "remove")
            result = self._dictionary_summary(policy)
            result["changed"] = changed
            return result
        if method == "dictionary.restore_defaults":
            return self._dictionary_summary(self.policy_store.restore_defaults())
        if method == "dictionary.import":
            source = params.get("source")
            if not isinstance(source, str) or not source.strip():
                raise ValueError("Dictionary import requires a source file")
            return self._dictionary_summary(self.policy_store.import_dictionary(Path(source)))
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
            return {"source": str(source), "candidates": candidates}
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
            runtime_root = get_application_runtime_root()
            cache_dir = (
                self.service.settings.runtime.whisper_cache
                or get_managed_whisper_cache_dir(runtime_root)
            )
            results = execute_install_plan(
                plan,
                approved_plan_id=plan_id,
                cache_dir=cache_dir,
            )
            installed_ids = {
                dependency_id
                for result in results
                for dependency_id in result.dependency_ids
            }
            settings = self.service.get_settings()
            runtime = dict(settings["runtime"])
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
            return [asdict(result) for result in results]
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
                or mode not in ("report_only", "censor")
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
                mode not in ("report_only", "censor")
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

    def _dictionary(self, policy: ProfanityPolicy | None = None) -> dict[str, object]:
        policy = policy or self.policy_store.load()
        words = sorted(policy.censor_words)
        exclusions = sorted(policy.exclusions)
        discovered = self._discovered_words(set(words), set(exclusions))
        return {
            "dictionary_path": str(policy.overrides_path),
            "schema_version": policy.schema_version,
            "seeded_from_default_version": policy.seeded_from_default_version,
            "words_count": len(words),
            "words": words,
            "exclusions_count": len(exclusions),
            "exclusions": exclusions,
            "discovered_count": len(discovered),
            "discovered": discovered,
        }

    def _dictionary_summary(self, policy: ProfanityPolicy | None = None) -> dict[str, object]:
        policy = policy or self.policy_store.load()
        return {
            "dictionary_path": str(policy.overrides_path),
            "schema_version": policy.schema_version,
            "seeded_from_default_version": policy.seeded_from_default_version,
            "words_count": len(policy.censor_words),
            "exclusions_count": len(policy.exclusions),
        }

    def _dictionary_entries(self, params: Mapping[str, Any]) -> dict[str, object]:
        target = params.get("target")
        if target not in ("censor", "exclude"):
            raise ValueError("Dictionary entries require a censor/exclude target")
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

        entries = list(self.policy_store.load().entries(target))
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

    def _discovered_words(self, censor_words: set[str], exclude_words: set[str]) -> list[str]:
        transcripts_directory = getattr(
            getattr(getattr(self.service, "settings", None), "directories", None),
            "transcripts",
            None,
        )
        if not isinstance(transcripts_directory, (str, Path)):
            return []

        discovered: set[str] = set()
        try:
            transcript_files = Path(transcripts_directory).glob("*-transcript.json")
            for transcript in transcript_files:
                try:
                    words_data = json.loads(transcript.read_text(encoding="utf-8"))
                    discovered.update(
                        candidate["word"]
                        for candidate in find_review_candidates(words_data, censor_words, exclude_words)
                    )
                except (OSError, TypeError, ValueError, ImportError):
                    continue
        except OSError:
            return []
        return sorted(discovered)


def serve(
    bridge: DesktopBridge | None = None,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> int:
    bridge = bridge or DesktopBridge()
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    try:
        for line in input_stream:
            if not line.strip():
                continue
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
            output_stream.write(json.dumps(response, separators=(",", ":")) + "\n")
            output_stream.flush()
    finally:
        bridge.close()
    return 0


def main() -> int:
    protocol_output = sys.stdout
    sys.stdout = sys.stderr
    return serve(output_stream=protocol_output)


if __name__ == "__main__":
    raise SystemExit(main())
