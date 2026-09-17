"""Dictionary pagination and review responses for the private desktop API."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any
from backend.policy import PolicyStore, ProfanityPolicy
from backend.censor import find_review_candidates
from backend.jobs.media import transcript_path
from backend.service import BackendService


class DictionaryController:
    """Adapt dictionary and transcript-review operations to the desktop protocol."""

    def __init__(self, service: BackendService, policy_store: PolicyStore):
        self.service = service
        self.policy_store = policy_store

    def handle(self, method: str, params: Mapping[str, Any] | None = None) -> object:
        params = params or {}
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
            # Match job artifact naming and reject sources outside the input root.
            transcript = transcript_path(
                source,
                self.service.settings.directories.transcripts,
                self.service.settings.directories.input,
            )
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
        raise ValueError(f"Unknown desktop bridge method: {method}")

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
