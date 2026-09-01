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
PolicyClassification = Literal["censor", "exclude", "none"]
PolicySource = Literal["default", "user", "imported"]
EPOCH_TIMESTAMP = "1970-01-01T00:00:00Z"


class PolicyFileError(RuntimeError):
    """Raised when the local user dictionary cannot be safely read or written."""

    def __init__(self, path: Path, detail: str):
        self.path = path
        self.detail = detail
        super().__init__(f"Dictionary file {path}: {detail}")


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
    overrides_path: Path
    overrides_count: int
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


def default_policy_path(
    environment: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    environment = os.environ if environment is None else environment
    configured = environment.get("CENSOR_POLICY_FILE", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return prepare_app_data_root(environment, home) / "dictionary" / "profanity.json"


class PolicyStore:
    """Own the complete durable dictionary, using shipped files only as templates."""

    def __init__(
        self,
        path: Path | None = None,
        *,
        censor_defaults_path: Path | None = None,
        exclusions_defaults_path: Path | None = None,
        legacy_path: Path | None = None,
    ):
        self.path = (path or default_policy_path()).expanduser().resolve()
        self.censor_path = self.path.with_name("censored.json")
        self.exclusions_path = self.path.with_name("exclusions.json")
        self.discovered_path = self.path.with_name("discovered.json")
        self.censor_defaults_path = (
            censor_defaults_path or get_profanity_censor_words_file()
        ).expanduser().resolve()
        self.exclusions_defaults_path = (
            exclusions_defaults_path or get_profanity_exclusions_file()
        ).expanduser().resolve()
        self.legacy_path = (
            legacy_path.expanduser().resolve()
            if legacy_path is not None
            else self.path.parent.parent / "policy.json"
        )

    def load(self) -> ProfanityPolicy:
        self._ensure_split_stores()
        censor_version, censor_entries = self._read_entry_store(self.censor_path)
        exclusion_version, exclusion_entries = self._read_entry_store(self.exclusions_path)
        return ProfanityPolicy(
            censor_words=frozenset(censor_entries),
            exclusions=frozenset(exclusion_entries),
            censor_defaults_path=self.censor_defaults_path,
            exclusions_defaults_path=self.exclusions_defaults_path,
            overrides_path=self.path,
            overrides_count=0,
            seeded_from_default_version=max(censor_version, exclusion_version),
            censor_entries=censor_entries,
            exclusion_entries=exclusion_entries,
        )

    def summary(self) -> dict[str, int | str]:
        self._ensure_split_stores()
        censor_version, censor_entries = self._read_entry_store(self.censor_path)
        exclusion_version, exclusion_entries = self._read_entry_store(self.exclusions_path)
        return {
            "dictionary_path": str(self.path.parent),
            "schema_version": POLICY_SCHEMA_VERSION,
            "seeded_from_default_version": max(censor_version, exclusion_version),
            "words_count": len(censor_entries),
            "exclusions_count": len(exclusion_entries),
        }

    def info(self) -> dict[str, int | str]:
        return {
            "dictionary_path": str(self.path.parent),
            "schema_version": POLICY_SCHEMA_VERSION,
            "seeded_from_default_version": DEFAULT_DICTIONARY_VERSION,
        }

    def initialize_discovered(self) -> None:
        if not self.discovered_path.exists():
            self.replace_discovered(set())

    def load_entries(self, target: PolicyTarget) -> tuple[PolicyEntry, ...]:
        if target not in ("censor", "exclude"):
            raise ValueError("Policy target must be censor or exclude")
        self._ensure_split_stores()
        path = self.censor_path if target == "censor" else self.exclusions_path
        _default_version, entries = self._read_entry_store(path)
        return tuple(entries.values())

    def load_discovered(self) -> tuple[str, ...]:
        if not self.discovered_path.exists():
            return ()
        return self._read_discovered(self.discovered_path)

    def _read_discovered(self, path: Path) -> tuple[str, ...]:
        payload = self._read_json(path)
        if not isinstance(payload, dict) or set(payload) != {"schema_version", "words"}:
            raise PolicyFileError(path, "must contain schema_version and words")
        if payload["schema_version"] != 1 or not isinstance(payload["words"], list):
            raise PolicyFileError(path, "has an unsupported format")
        words = {normalize_policy_word(word) for word in payload["words"] if isinstance(word, str)}
        if len(words) != len(payload["words"]):
            raise PolicyFileError(path, "words must be unique normalized strings")
        return tuple(sorted(words))

    def replace_discovered(self, values: set[str]) -> tuple[str, ...]:
        words = sorted({normalize_policy_word(value) for value in values})
        self._write_json_atomic(
            self.discovered_path,
            {"schema_version": 1, "words": words},
            self._read_discovered,
        )
        return tuple(words)

    def add_discovered(self, values: set[str]) -> tuple[str, ...]:
        return self.replace_discovered(set(self.load_discovered()) | values)

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

    def restore_defaults(self) -> ProfanityPolicy:
        censor_words, exclusions = self._load_defaults()
        self._write_dictionary(
            censor_words,
            exclusions,
            seeded_from_default_version=DEFAULT_DICTIONARY_VERSION,
            source="default",
        )
        return self.load()

    def import_dictionary(self, source: Path) -> ProfanityPolicy:
        imported = self._read_dictionary(source.expanduser().resolve())
        self._write_dictionary(
            set(imported.censor_words),
            set(imported.exclusions),
            seeded_from_default_version=imported.seeded_from_default_version,
            source="imported",
        )
        return self.load()

    def export_dictionary(self, destination: Path) -> Path:
        policy = self.load()
        destination = destination.expanduser().resolve()
        self._write_payload(destination, self._payload(policy))
        return destination

    def _ensure_split_stores(self) -> None:
        if self.censor_path.exists() and self.exclusions_path.exists():
            return
        if not self.censor_path.exists() and not self.exclusions_path.exists() and self.path.exists():
            policy = self._read_dictionary(self.path)
            self._write_dictionary(
                set(policy.censor_words),
                set(policy.exclusions),
                seeded_from_default_version=policy.seeded_from_default_version,
                censor_entries=policy.censor_entries,
                exclusion_entries=policy.exclusion_entries,
            )
            return
        if not self.censor_path.exists() and not self.exclusions_path.exists():
            self._initialize()
            return
        censor_words, exclusions = self._load_defaults()
        if not self.censor_path.exists():
            entries = {word: PolicyEntry(word, EPOCH_TIMESTAMP, "default") for word in censor_words}
            self._write_entry_store(self.censor_path, entries, DEFAULT_DICTIONARY_VERSION)
        if not self.exclusions_path.exists():
            entries = {word: PolicyEntry(word, EPOCH_TIMESTAMP, "default") for word in exclusions}
            self._write_entry_store(self.exclusions_path, entries, DEFAULT_DICTIONARY_VERSION)

    def _initialize(self) -> None:
        censor_words, exclusions = self._load_defaults()
        if self.legacy_path.is_file():
            overrides = self._read_legacy_overrides()
            censor_words, exclusions = self._materialize(censor_words, exclusions, overrides)
        self._write_dictionary(
            censor_words,
            exclusions,
            seeded_from_default_version=DEFAULT_DICTIONARY_VERSION,
            source="default",
        )

    def _load_defaults(self) -> tuple[set[str], set[str]]:
        try:
            exclusions = load_profanity_exclusions(self.exclusions_defaults_path)
            censor_words = load_profanity_censor_words(self.censor_defaults_path) - exclusions
        except (OSError, ValueError) as exc:
            raise PolicyFileError(self.path, f"could not load bundled defaults: {exc}") from exc
        return censor_words, exclusions

    @staticmethod
    def _materialize(
        censor_defaults: set[str],
        exclusion_defaults: set[str],
        overrides: dict[str, PolicyClassification],
    ) -> tuple[set[str], set[str]]:
        censor_words = set(censor_defaults) - exclusion_defaults
        exclusions = set(exclusion_defaults)
        for word, classification in overrides.items():
            censor_words.discard(word)
            exclusions.discard(word)
            if classification == "censor":
                censor_words.add(word)
            elif classification == "exclude":
                exclusions.add(word)
        return censor_words, exclusions

    def _read_legacy_overrides(self) -> dict[str, PolicyClassification]:
        payload = self._read_json(self.legacy_path)
        if not isinstance(payload, dict) or set(payload) != {"schema_version", "overrides"}:
            raise PolicyFileError(
                self.legacy_path,
                "must contain only schema_version and overrides",
            )
        if payload["schema_version"] != 1:
            raise PolicyFileError(
                self.legacy_path,
                f"unsupported schema version {payload['schema_version']!r}",
            )
        raw_overrides = payload["overrides"]
        if not isinstance(raw_overrides, dict):
            raise PolicyFileError(self.legacy_path, "overrides must be an object")

        overrides: dict[str, PolicyClassification] = {}
        for raw_word, classification in raw_overrides.items():
            if not isinstance(raw_word, str) or classification not in (
                "censor",
                "exclude",
                "none",
            ):
                raise PolicyFileError(
                    self.legacy_path,
                    "contains an invalid word classification",
                )
            try:
                word = normalize_policy_word(raw_word)
            except ValueError as exc:
                raise PolicyFileError(self.legacy_path, str(exc)) from exc
            if word != raw_word:
                raise PolicyFileError(
                    self.legacy_path,
                    f"contains a non-normalized word: {raw_word!r}",
                )
            overrides[word] = classification
        return overrides

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
            overrides_path=self.path,
            overrides_count=0,
            schema_version=schema_version,
            seeded_from_default_version=default_version,
            censor_entries=censor_entries,
            exclusion_entries=exclusion_entries,
        )

    @staticmethod
    def _validated_payload(path: Path) -> dict[str, object]:
        payload = PolicyStore._read_json(path)
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
        if isinstance(schema_version, bool) or schema_version not in (1, POLICY_SCHEMA_VERSION):
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
            if schema_version == 1:
                raw_word = raw_entry
                added_at = EPOCH_TIMESTAMP
                source: PolicySource = "default"
            elif isinstance(raw_entry, dict) and set(raw_entry) == {"value", "added_at", "source"}:
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

    @staticmethod
    def _read_json(path: Path) -> object:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise PolicyFileError(
                path,
                f"invalid JSON at line {exc.lineno}, column {exc.colno}",
            ) from exc
        except OSError as exc:
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
        if self.discovered_path.exists():
            classified = set(censor_entries) | set(exclusion_entries)
            self.replace_discovered(set(self.load_discovered()) - classified)

    def _write_policy(self, policy: ProfanityPolicy) -> None:
        self._write_dictionary(
            set(policy.censor_words),
            set(policy.exclusions),
            seeded_from_default_version=policy.seeded_from_default_version,
            censor_entries=policy.censor_entries,
            exclusion_entries=policy.exclusion_entries,
        )

    def _read_entry_store(self, path: Path) -> tuple[int, dict[str, PolicyEntry]]:
        payload = self._read_json(path)
        required_keys = {"schema_version", "seeded_from_default_version", "entries"}
        if not isinstance(payload, dict) or set(payload) != required_keys:
            raise PolicyFileError(path, f"must contain only {', '.join(sorted(required_keys))}")
        if payload["schema_version"] != POLICY_SCHEMA_VERSION:
            raise PolicyFileError(path, f"unsupported schema version {payload['schema_version']!r}")
        default_version = payload["seeded_from_default_version"]
        if isinstance(default_version, bool) or not isinstance(default_version, int) or default_version < 1:
            raise PolicyFileError(path, "seeded_from_default_version must be a positive integer")
        entries = self._validate_entries(path, "entries", payload["entries"], POLICY_SCHEMA_VERSION)
        return default_version, entries

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
            os.replace(temporary_path, path)
            temporary_path = None
        except PolicyFileError:
            raise
        except OSError as exc:
            raise PolicyFileError(path, str(exc)) from exc
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
