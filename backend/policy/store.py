"""Durable, user-owned profanity dictionary persistence."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal

from backend.application_identity import prepare_app_data_root
from .errors import PolicyFileError
from .transactions import STORE_NAMES, JOURNAL_NAME, LOCK_NAME, transactional
from backend.runtime import (
    get_profanity_censor_words_file,
    get_profanity_exclusions_file,
    load_profanity_censor_words,
    load_profanity_exclusions,
    normalize_policy_word,
)


POLICY_SCHEMA_VERSION = 2
DEFAULT_DICTIONARY_VERSION = 1
PolicyTarget = Literal["censor", "exclude"]
PolicyAction = Literal["add", "remove"]
PolicySource = Literal["default", "user", "imported"]
EPOCH_TIMESTAMP = "1970-01-01T00:00:00Z"


@dataclass(frozen=True)
class PolicyEntry:
    value: str
    added_at: str
    source: PolicySource


@dataclass(frozen=True)
class ProfanityPolicy:
    censor_words: frozenset[str]
    exclusions: frozenset[str]
    censor_defaults_path: Path
    exclusions_defaults_path: Path
    dictionary_path: Path
    schema_version: int = POLICY_SCHEMA_VERSION
    seeded_from_default_version: int = DEFAULT_DICTIONARY_VERSION
    censor_entries: Mapping[str, PolicyEntry] = field(default_factory=dict)
    exclusion_entries: Mapping[str, PolicyEntry] = field(default_factory=dict)

    def classification(self, word: str) -> PolicyTarget | None:
        if word in self.exclusions:
            return "exclude"
        if word in self.censor_words:
            return "censor"
        return None

    def entries(self, target: PolicyTarget) -> tuple[PolicyEntry, ...]:
        metadata = self.censor_entries if target == "censor" else self.exclusion_entries
        words = self.censor_words if target == "censor" else self.exclusions
        return tuple(
            metadata.get(word, PolicyEntry(word, EPOCH_TIMESTAMP, "default"))
            for word in words
        )


def default_dictionary_directory(
    environment: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    return prepare_app_data_root(environment, home) / "dictionary"


class PolicyStore:
    """Own the complete durable dictionary, using shipped files only as templates."""

    def __init__(
        self,
        directory: Path | None = None,
        *,
        censor_defaults_path: Path | None = None,
        exclusions_defaults_path: Path | None = None,
        lock_timeout: float = 5.0,
    ):
        self.lock_timeout = lock_timeout
        self._pending: dict[str, dict] | None = None
        self.directory = (directory or default_dictionary_directory()).expanduser().resolve()
        self.censor_path = self.directory / "censored.json"
        self.exclusions_path = self.directory / "exclusions.json"
        self.discovered_path = self.directory / "discovered.json"
        self.censor_defaults_path = (
            censor_defaults_path or get_profanity_censor_words_file()
        ).expanduser().resolve()
        self.exclusions_defaults_path = (
            exclusions_defaults_path or get_profanity_exclusions_file()
        ).expanduser().resolve()

    @transactional
    def load(self) -> ProfanityPolicy:
        self._ensure_split_stores()
        censor_version, censor_entries = self._read_entry_store(self.censor_path)
        exclusion_version, exclusion_entries = self._read_entry_store(self.exclusions_path)
        if set(censor_entries) & set(exclusion_entries):
            raise PolicyFileError(self.directory, "Censored and excluded entries overlap; restore a valid backup.")
        return ProfanityPolicy(
            censor_words=frozenset(censor_entries),
            exclusions=frozenset(exclusion_entries),
            censor_defaults_path=self.censor_defaults_path,
            exclusions_defaults_path=self.exclusions_defaults_path,
            dictionary_path=self.directory,
            seeded_from_default_version=max(censor_version, exclusion_version),
            censor_entries=censor_entries,
            exclusion_entries=exclusion_entries,
        )

    @transactional
    def info(self) -> dict[str, int | str]:
        return {
            "dictionary_path": str(self.directory),
            "schema_version": POLICY_SCHEMA_VERSION,
            "seeded_from_default_version": DEFAULT_DICTIONARY_VERSION,
        }

    @transactional
    def initialize_discovered(self) -> None:
        if not self._exists(self.discovered_path):
            self._write_json_atomic(self.discovered_path, {"schema_version": 1, "words": []}, self._read_discovered)

    @transactional
    def load_entries(self, target: PolicyTarget) -> tuple[PolicyEntry, ...]:
        if target not in ("censor", "exclude"):
            raise ValueError("Policy target must be censor or exclude")
        self._ensure_entry_store(target)
        path = self.censor_path if target == "censor" else self.exclusions_path
        _default_version, entries = self._read_entry_store(path)
        return tuple(entries.values())

    @transactional
    def load_discovered(self) -> tuple[str, ...]:
        if not self._exists(self.discovered_path):
            return ()
        return self._read_discovered(self.discovered_path)

    def _read_discovered(self, path: Path) -> tuple[str, ...]:
        return self._validate_discovered(path, self._read_json(path))

    def _validate_discovered(self, path: Path, payload: object) -> tuple[str, ...]:
        if not isinstance(payload, dict) or set(payload) != {"schema_version", "words"}:
            raise PolicyFileError(path, "must contain schema_version and words")
        if type(payload["schema_version"]) is not int or payload["schema_version"] != 1 or not isinstance(payload["words"], list):
            raise PolicyFileError(path, "has an unsupported format")
        try:
            words = {normalize_policy_word(word) for word in payload["words"] if isinstance(word, str)}
        except ValueError as exc:
            raise PolicyFileError(path, "words must be normalized strings") from exc
        if len(words) != len(payload["words"]) or sorted(words) != sorted(payload["words"]):
            raise PolicyFileError(path, "words must be unique normalized strings")
        return tuple(sorted(words))

    @transactional
    def replace_discovered(self, values: set[str]) -> tuple[str, ...]:
        policy = self.load()
        words = sorted({normalize_policy_word(value) for value in values} - policy.censor_words - policy.exclusions)
        self._write_json_atomic(
            self.discovered_path,
            {"schema_version": 1, "words": words},
            self._read_discovered,
        )
        return tuple(words)

    @transactional
    def add_discovered(self, values: set[str]) -> tuple[str, ...]:
        policy = self.load()
        classified = set(policy.censor_words) | set(policy.exclusions)
        words = {
            normalize_policy_word(value)
            for value in self.load_discovered()
        } | {
            normalize_policy_word(value)
            for value in values
        }
        return self.replace_discovered(words - classified)

    @transactional
    def update(
        self,
        target: PolicyTarget,
        value: str,
        action: PolicyAction,
    ) -> tuple[ProfanityPolicy, bool]:
        if target not in ("censor", "exclude"):
            raise ValueError("Policy target must be censor or exclude")
        if action not in ("add", "remove"):
            raise ValueError("Policy action must be add or remove")

        word = normalize_policy_word(value)
        before = self.load()
        desired: PolicyTarget | None = target if action == "add" else None
        if before.classification(word) == desired:
            return before, False

        censor_words = set(before.censor_words)
        exclusions = set(before.exclusions)
        censor_entries = dict(before.censor_entries)
        exclusion_entries = dict(before.exclusion_entries)
        censor_words.discard(word)
        exclusions.discard(word)
        censor_entries.pop(word, None)
        exclusion_entries.pop(word, None)
        if desired == "censor":
            censor_words.add(word)
            censor_entries[word] = self._entry(word, "user")
        elif desired == "exclude":
            exclusions.add(word)
            exclusion_entries[word] = self._entry(word, "user")
        self._write_entry_store(
            self.exclusions_path,
            exclusion_entries,
            before.seeded_from_default_version,
        )
        self._write_entry_store(
            self.censor_path,
            censor_entries,
            before.seeded_from_default_version,
        )
        if action == "add":
            self.replace_discovered(set(self.load_discovered()) - {word})
        return self.load(), True

    @transactional
    def restore_defaults(self) -> ProfanityPolicy:
        censor_words, exclusions = self._load_defaults()
        self._write_dictionary(
            censor_words,
            exclusions,
            seeded_from_default_version=DEFAULT_DICTIONARY_VERSION,
            source="default",
        )
        return self.load()

    @transactional
    def import_dictionary(self, source: Path) -> ProfanityPolicy:
        imported = self._read_dictionary(source.expanduser().resolve())
        self._write_dictionary(
            set(imported.censor_words),
            set(imported.exclusions),
            seeded_from_default_version=imported.seeded_from_default_version,
            source="imported",
        )
        return self.load()

    @transactional
    def export_dictionary(self, destination: Path) -> Path:
        policy = self.load()
        destination = destination.expanduser().resolve()
        self.validate_export_destination(destination)
        self._write_payload(destination, self._payload(policy))
        return destination

    def validate_export_destination(self, destination: Path) -> None:
        """Portable exports must never replace managed policy or ownership files."""
        reserved = {self.directory / name for name in STORE_NAMES | {JOURNAL_NAME, LOCK_NAME}}
        if destination.expanduser().resolve() in reserved:
            raise PolicyFileError(destination, "Choose an export destination outside the dictionary stores.")

    @transactional
    def export_payload(self) -> dict:
        """Give a guarded publisher the same portable document as the explicit CLI export."""
        return self._payload(self.load())

    def _ensure_split_stores(self) -> None:
        self._ensure_entry_store("censor")
        self._ensure_entry_store("exclude")

    def _ensure_entry_store(self, target: PolicyTarget) -> None:
        path = self.censor_path if target == "censor" else self.exclusions_path
        if self._exists(path):
            return
        try:
            if target == "exclude":
                words = load_profanity_exclusions(self.exclusions_defaults_path)
            else:
                exclusions = load_profanity_exclusions(self.exclusions_defaults_path)
                words = load_profanity_censor_words(self.censor_defaults_path) - exclusions
        except (OSError, ValueError) as exc:
            raise PolicyFileError(path, f"could not load bundled defaults: {exc}") from exc
        entries = {word: PolicyEntry(word, EPOCH_TIMESTAMP, "default") for word in words}
        self._write_entry_store(path, entries, DEFAULT_DICTIONARY_VERSION)

    def _load_defaults(self) -> tuple[set[str], set[str]]:
        try:
            exclusions = load_profanity_exclusions(self.exclusions_defaults_path)
            censor_words = load_profanity_censor_words(self.censor_defaults_path) - exclusions
        except (OSError, ValueError) as exc:
            raise PolicyFileError(self.directory, f"could not load bundled defaults: {exc}") from exc
        return censor_words, exclusions


    def _read_dictionary(self, path: Path) -> ProfanityPolicy:
        payload = self._validated_payload(path)
        schema_version = payload["schema_version"]
        default_version = payload["seeded_from_default_version"]
        censor_entries = self._validate_entries(path, "words", payload["words"], schema_version)
        exclusion_entries = self._validate_entries(path, "exclusions", payload["exclusions"], schema_version)
        censor_words = set(censor_entries)
        exclusions = set(exclusion_entries)
        overlap = censor_words & exclusions
        if overlap:
            raise PolicyFileError(path, f"words and exclusions overlap: {sorted(overlap)[0]!r}")
        return ProfanityPolicy(
            censor_words=frozenset(censor_words),
            exclusions=frozenset(exclusions),
            censor_defaults_path=self.censor_defaults_path,
            exclusions_defaults_path=self.exclusions_defaults_path,
            dictionary_path=self.directory,
            schema_version=schema_version,
            seeded_from_default_version=default_version,
            censor_entries=censor_entries,
            exclusion_entries=exclusion_entries,
        )

    def _validated_payload(self, path: Path) -> dict[str, object]:
        payload = self._read_json(path)
        required_keys = {
            "schema_version",
            "seeded_from_default_version",
            "words",
            "exclusions",
        }
        if not isinstance(payload, dict) or set(payload) != required_keys:
            raise PolicyFileError(path, f"must contain only {', '.join(sorted(required_keys))}")
        schema_version = payload["schema_version"]
        default_version = payload["seeded_from_default_version"]
        if isinstance(schema_version, bool) or schema_version != POLICY_SCHEMA_VERSION:
            raise PolicyFileError(path, f"unsupported schema version {schema_version!r}")
        if isinstance(default_version, bool) or not isinstance(default_version, int) or default_version < 1:
            raise PolicyFileError(path, "seeded_from_default_version must be a positive integer")
        return payload

    @classmethod
    def _validate_entries(
        cls,
        path: Path,
        name: str,
        value: object,
        schema_version: int,
    ) -> dict[str, PolicyEntry]:
        if not isinstance(value, list):
            raise PolicyFileError(path, f"{name} must be an array")
        entries: dict[str, PolicyEntry] = {}
        for raw_entry in value:
            if isinstance(raw_entry, dict) and set(raw_entry) == {"value", "added_at", "source"}:
                raw_word = raw_entry["value"]
                added_at = raw_entry["added_at"]
                source = raw_entry["source"]
            else:
                raise PolicyFileError(path, f"{name} must contain dictionary entries")
            if not isinstance(raw_word, str):
                raise PolicyFileError(path, f"{name} must contain only strings")
            try:
                word = normalize_policy_word(raw_word)
            except ValueError as exc:
                raise PolicyFileError(path, str(exc)) from exc
            if word != raw_word:
                raise PolicyFileError(path, f"contains a non-normalized word: {raw_word!r}")
            if word in entries:
                raise PolicyFileError(path, f"{name} contains duplicate word: {word!r}")
            if not isinstance(added_at, str) or not cls._valid_timestamp(added_at):
                raise PolicyFileError(path, f"{name} contains an invalid added_at timestamp")
            if source not in ("default", "user", "imported"):
                raise PolicyFileError(path, f"{name} contains an invalid source")
            entries[word] = PolicyEntry(word, added_at, source)
        return entries

    @staticmethod
    def _valid_timestamp(value: str) -> bool:
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            return True
        except ValueError:
            return False

    def _exists(self, path: Path) -> bool:
        return (self._pending is not None and path.name in self._pending) or path.exists()

    def _read_json(self, path: Path) -> object:
        if self._pending is not None and path.parent == self.directory and path.name in self._pending:
            return self._pending[path.name]
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise PolicyFileError(
                path,
                f"invalid JSON at line {exc.lineno}, column {exc.colno}",
            ) from exc
        except (OSError, UnicodeError) as exc:
            raise PolicyFileError(path, str(exc)) from exc

    def _write_dictionary(
        self,
        censor_words: set[str],
        exclusions: set[str],
        *,
        seeded_from_default_version: int,
        source: PolicySource | None = None,
        censor_entries: Mapping[str, PolicyEntry] | None = None,
        exclusion_entries: Mapping[str, PolicyEntry] | None = None,
    ) -> None:
        censor_entries = dict(censor_entries or {})
        exclusion_entries = dict(exclusion_entries or {})
        if source is not None:
            added_at = EPOCH_TIMESTAMP if source == "default" else self._timestamp()
            censor_entries = {word: PolicyEntry(word, added_at, source) for word in censor_words}
            exclusion_entries = {word: PolicyEntry(word, added_at, source) for word in exclusions}
        self._write_entry_store(self.censor_path, censor_entries, seeded_from_default_version)
        self._write_entry_store(self.exclusions_path, exclusion_entries, seeded_from_default_version)
        if self._exists(self.discovered_path):
            classified = set(censor_entries) | set(exclusion_entries)
            self.replace_discovered(set(self.load_discovered()) - classified)

    def _read_entry_store(self, path: Path) -> tuple[int, dict[str, PolicyEntry]]:
        return self._validate_entry_store(path, self._read_json(path))

    def _validate_entry_store(self, path: Path, payload: object) -> tuple[int, dict[str, PolicyEntry]]:
        required_keys = {"schema_version", "seeded_from_default_version", "entries"}
        if not isinstance(payload, dict) or set(payload) != required_keys:
            raise PolicyFileError(path, f"must contain only {', '.join(sorted(required_keys))}")
        if type(payload["schema_version"]) is not int or payload["schema_version"] != POLICY_SCHEMA_VERSION:
            raise PolicyFileError(path, f"unsupported schema version {payload['schema_version']!r}")
        default_version = payload["seeded_from_default_version"]
        if isinstance(default_version, bool) or not isinstance(default_version, int) or default_version < 1:
            raise PolicyFileError(path, "seeded_from_default_version must be a positive integer")
        entries = self._validate_entries(path, "entries", payload["entries"], POLICY_SCHEMA_VERSION)
        return default_version, entries

    def _validate_store_payload(self, path: Path, payload: object) -> object:
        if path.name == "discovered.json":
            return self._validate_discovered(path, payload)
        return self._validate_entry_store(path, payload)

    def _write_entry_store(
        self,
        path: Path,
        entries: Mapping[str, PolicyEntry],
        seeded_from_default_version: int,
    ) -> None:
        payload = {
            "schema_version": POLICY_SCHEMA_VERSION,
            "seeded_from_default_version": seeded_from_default_version,
            "entries": [
                {"value": entry.value, "added_at": entry.added_at, "source": entry.source}
                for entry in sorted(entries.values(), key=lambda item: item.value)
            ],
        }
        self._write_json_atomic(path, payload, self._read_entry_store)

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    @classmethod
    def _entry(cls, value: str, source: PolicySource) -> PolicyEntry:
        return PolicyEntry(value, cls._timestamp(), source)

    @staticmethod
    def _payload(policy: ProfanityPolicy) -> dict[str, object]:
        return {
            "schema_version": POLICY_SCHEMA_VERSION,
            "seeded_from_default_version": policy.seeded_from_default_version,
            "words": [
                {"value": entry.value, "added_at": entry.added_at, "source": entry.source}
                for entry in sorted(policy.entries("censor"), key=lambda item: item.value)
            ],
            "exclusions": [
                {"value": entry.value, "added_at": entry.added_at, "source": entry.source}
                for entry in sorted(policy.entries("exclude"), key=lambda item: item.value)
            ],
        }

    def _write_payload(self, path: Path, payload: dict[str, object]) -> None:
        self._write_json_atomic(path, payload, self._read_dictionary)

    def _write_json_atomic(
        self,
        path: Path,
        payload: dict[str, object],
        validate: Callable[[Path], object],
    ) -> None:
        if self._pending is not None and path.parent == self.directory and path.name in STORE_NAMES:
            self._validate_store_payload(path, payload)
            self._pending[path.name] = payload
            return
        temporary_path: Path | None = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                json.dump(payload, temporary_file, indent=2, sort_keys=True)
                temporary_file.write("\n")
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
                temporary_path = Path(temporary_file.name)

            validate(temporary_path)
            # Portable exports are single-file snapshots; managed stores use the journal.
            os.replace(temporary_path, path)
            temporary_path = None
        except PolicyFileError:
            raise
        except (OSError, UnicodeError) as exc:
            raise PolicyFileError(path, str(exc)) from exc
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
