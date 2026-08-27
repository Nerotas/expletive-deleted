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
    build_install_plan,
    execute_install_plan,
    get_profanity_censor_words_file,
    get_profanity_exclusions_file,
    get_whisper_cache_dir,
    load_profanity_censor_words,
    load_profanity_exclusions,
)
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
            words_path = get_profanity_censor_words_file()
            exclusions_path = get_profanity_exclusions_file()
            return {
                "words_path": str(words_path),
                "words_count": len(load_profanity_censor_words(words_path)),
                "exclusions_path": str(exclusions_path),
                "exclusions_count": len(load_profanity_exclusions(exclusions_path)),
            }
        if method == "dependencies.plan":
            plan = build_install_plan(
                list(params["components"]),
                cache_dir=self.service.settings.runtime.whisper_cache or get_whisper_cache_dir(),
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
        if method == "jobs.list":
            return [job.to_dict() for job in self.service.jobs.list()]
        if method == "jobs.submit":
            mode = params.get("mode")
            job = self.service.submit_job(Path(params["source"]), mode)
            return job.to_dict()
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