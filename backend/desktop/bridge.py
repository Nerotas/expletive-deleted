"""Composition root for the private desktop application API."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any
from backend.policy import PolicyStore
from backend.service import BackendService
from backend.settings import SettingsStore
from backend.settings.transactions import validate_base
from .dictionary import DictionaryController
from .installation import InstallationController
from .native_files import NativeFiles


class DesktopBridge:
    """Route private requests without owning feature-specific worker state."""

    def __init__(self, service: BackendService | None = None, policy_store: PolicyStore | None = None):
        store = service.store if service is not None else SettingsStore()
        self._settings_owner = store.desktop_owner()
        self._settings_owner.__enter__()
        self._closed = False
        try:
            # Acquire ownership before loading settings so a CLI edit cannot slip
            # between the startup snapshot and the desktop's active-job guards.
            self.service = service if service is not None else BackendService(store)
            self.policy_store = policy_store or PolicyStore()
            self.installations = InstallationController(self.service)
            self.dictionary = DictionaryController(self.service, self.policy_store)
            self.native_files = NativeFiles(self.service, self.policy_store)
        except Exception:
            self._settings_owner.__exit__(None, None, None)
            raise

    def handle(self, method: str, params: Mapping[str, Any] | None = None) -> object:
        params = params or {}
        if method.startswith('native.'):
            return self.native_files.handle(method, params)
        if method.startswith("dependencies."):
            return self.installations.handle(method, params)
        if method.startswith("dictionary.") or method == "reviews.list":
            return self.dictionary.handle(method, params)
        if method == "settings.get":
            return self.service.get_settings_snapshot()
        if method == "settings.update":
            return self.service.update_settings(params["settings"], validate_base(params.get("base")))
        if method == "settings.patch":
            strict = params.get("strict", False)
            if not isinstance(strict, bool):
                raise ValueError("Settings resolution requires a boolean strict flag")
            return self.service.patch_settings(params.get("revision"), params.get("changes"), strict=strict)
        if method == "capabilities.get":
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
        if method == "downloads.list":
            return [job.to_dict() for job in self.service.downloads.list()]
        if method == "downloads.submit":
            url = params.get("url")
            retry_id = params.get("retry_id")
            cookie_browser = params.get("cookie_browser")
            if not isinstance(url, str) or (retry_id is not None and not isinstance(retry_id, str)) or (cookie_browser is not None and cookie_browser not in {"brave", "chrome", "edge", "firefox"}):
                raise ValueError("YouTube download requires a video URL")
            return self.service.submit_youtube_download(url, retry_id, cookie_browser).to_dict()
        if method == "downloads.events":
            return [event.to_dict() for event in self.service.downloads.events(params["job_id"])]
        if method == "downloads.cancel":
            return self.service.downloads.cancel(params["job_id"]).to_dict()
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
        if self._closed:
            return
        self._closed = True
        self.native_files.close()
        self.installations.cancel_pending()
        # Do not wait for setup before giving media jobs their cancellation signal.
        try:
            self.service.close()
        finally:
            self.installations.close()
            self._settings_owner.__exit__(None, None, None)
