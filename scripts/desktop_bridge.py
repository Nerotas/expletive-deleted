#!/usr/bin/env python3
"""Expose BackendService to Electron over a private JSON-lines child process."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any, TextIO

from backend.runtime import (
    add_word_to_list,
    build_install_plan,
    execute_install_plan,
    get_profanity_censor_words_file,
    get_profanity_exclusions_file,
    get_whisper_cache_dir,
    load_profanity_censor_words,
    load_profanity_exclusions,
    remove_word_from_list,
)
from backend.censor import find_review_candidates
from backend.jobs.media import transcript_path
from backend.service import BackendService


class DesktopBridge:
    def __init__(self, service: BackendService | None = None):
        self.service = service or BackendService()
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
        if method == "dictionary.add":
            target = params.get("target")
            word = params.get("word")
            if target not in ("censor", "exclude") or not isinstance(word, str):
                raise ValueError("Dictionary updates require a censor/exclude target and a word")
            path, description = self._dictionary_target(target)
            _, added = add_word_to_list(path, word, description)
            result = self._dictionary()
            result["changed"] = added
            return result
        if method == "dictionary.remove":
            target = params.get("target")
            word = params.get("word")
            if target not in ("censor", "exclude") or not isinstance(word, str):
                raise ValueError("Dictionary updates require a censor/exclude target and a word")
            path, description = self._dictionary_target(target)
            _, removed = remove_word_from_list(path, word, description)
            result = self._dictionary()
            result["changed"] = removed
            return result
        if method == "reviews.list":
            source = Path(params["source"]).expanduser().resolve()
            transcript = transcript_path(source, self.service.settings.directories.transcripts)
            if not transcript.is_file():
                raise ValueError("No transcript is available for this file. Run Report only first.")
            try:
                words_data = json.loads(transcript.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Transcript could not be read: {transcript}") from exc
            candidates = find_review_candidates(
                words_data,
                load_profanity_censor_words(get_profanity_censor_words_file()),
                load_profanity_exclusions(get_profanity_exclusions_file()),
            )
            return {"source": str(source), "candidates": candidates}
        if method == "dependencies.plan":
            plan = build_install_plan(
                list(params["components"]),
                cache_dir=self.service.settings.runtime.whisper_cache or get_whisper_cache_dir(),
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
                    }
                    for action in plan.actions
                ],
            }
        if method == "dependencies.install":
            plan_id = params["plan_id"]
            plan = self._install_plans.get(plan_id)
            if plan is None:
                raise ValueError("Dependency plan is unknown or expired; review it again")
            results = execute_install_plan(
                plan,
                approved_plan_id=plan_id,
                cache_dir=self.service.settings.runtime.whisper_cache or get_whisper_cache_dir(),
            )
            return [asdict(result) for result in results]
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
            if not isinstance(source, str) or mode not in ("report_only", "censor"):
                raise ValueError("Job submission requires a source and supported mode")
            job = self.service.submit_job(Path(source), mode)
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

    @staticmethod
    def _dictionary_target(target: str) -> tuple[Path, str]:
        if target == "censor":
            return get_profanity_censor_words_file(), "Profanity censor words"
        return get_profanity_exclusions_file(), "Profanity exclusions"

    def _dictionary(self) -> dict[str, object]:
        words_path = get_profanity_censor_words_file()
        exclusions_path = get_profanity_exclusions_file()
        words = sorted(load_profanity_censor_words(words_path))
        exclusions = sorted(load_profanity_exclusions(exclusions_path))
        discovered = self._discovered_words(set(words), set(exclusions))
        return {
            "words_path": str(words_path),
            "words_count": len(words),
            "words": words,
            "exclusions_path": str(exclusions_path),
            "exclusions_count": len(exclusions),
            "exclusions": exclusions,
            "discovered_count": len(discovered),
            "discovered": discovered,
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
