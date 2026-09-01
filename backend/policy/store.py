"""Durable, user-owned profanity dictionary persistence."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from backend.application_identity import prepare_app_data_root
from backend.runtime import (
    get_profanity_censor_words_file,
    get_profanity_exclusions_file,
    load_profanity_censor_words,
    load_profanity_exclusions,
    normalize_policy_word,
)


POLICY_SCHEMA_VERSION = 1
DEFAULT_DICTIONARY_VERSION = 1
PolicyTarget = Literal["censor", "exclude"]
PolicyAction = Literal["add", "remove"]
PolicyClassification = Literal["censor", "exclude", "none"]


class PolicyFileError(RuntimeError):
    """Raised when the local user dictionary cannot be safely read or written."""

    def __init__(self, path: Path, detail: str):
        self.path = path
        self.detail = detail
        super().__init__(f"Dictionary file {path}: {detail}")


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

    def classification(self, word: str) -> PolicyTarget | None:
        if word in self.exclusions:
            return "exclude"
        if word in self.censor_words:
            return "censor"
        return None


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
        if not self.path.exists():
            self._initialize()
        return self._read_dictionary(self.path)

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
        censor_words.discard(word)
        exclusions.discard(word)
        if desired == "censor":
            censor_words.add(word)
        elif desired == "exclude":
            exclusions.add(word)
        self._write_dictionary(
            censor_words,
            exclusions,
            seeded_from_default_version=before.seeded_from_default_version,
        )
        return self.load(), True

    def restore_defaults(self) -> ProfanityPolicy:
        censor_words, exclusions = self._load_defaults()
        self._write_dictionary(
            censor_words,
            exclusions,
            seeded_from_default_version=DEFAULT_DICTIONARY_VERSION,
        )
        return self.load()

    def import_dictionary(self, source: Path) -> ProfanityPolicy:
        imported = self._read_dictionary(source.expanduser().resolve())
        self._write_dictionary(
            set(imported.censor_words),
            set(imported.exclusions),
            seeded_from_default_version=imported.seeded_from_default_version,
        )
        return self.load()

    def export_dictionary(self, destination: Path) -> Path:
        policy = self.load()
        destination = destination.expanduser().resolve()
        self._write_payload(destination, self._payload(policy))
        return destination

    def _initialize(self) -> None:
        censor_words, exclusions = self._load_defaults()
        if self.legacy_path.is_file():
            overrides = self._read_legacy_overrides()
            censor_words, exclusions = self._materialize(censor_words, exclusions, overrides)
        self._write_dictionary(
            censor_words,
            exclusions,
            seeded_from_default_version=DEFAULT_DICTIONARY_VERSION,
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
        if payload["schema_version"] != POLICY_SCHEMA_VERSION:
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
        censor_words = self._validate_word_array(path, "words", payload["words"])
        exclusions = self._validate_word_array(path, "exclusions", payload["exclusions"])
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
        )

    @staticmethod
    def _validate_word_array(path: Path, name: str, value: object) -> set[str]:
        if not isinstance(value, list):
            raise PolicyFileError(path, f"{name} must be an array")
        words: set[str] = set()
        for raw_word in value:
            if not isinstance(raw_word, str):
                raise PolicyFileError(path, f"{name} must contain only strings")
            try:
                word = normalize_policy_word(raw_word)
            except ValueError as exc:
                raise PolicyFileError(path, str(exc)) from exc
            if word != raw_word:
                raise PolicyFileError(path, f"contains a non-normalized word: {raw_word!r}")
            if word in words:
                raise PolicyFileError(path, f"{name} contains duplicate word: {word!r}")
            words.add(word)
        return words

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
    ) -> None:
        policy = ProfanityPolicy(
            censor_words=frozenset(censor_words),
            exclusions=frozenset(exclusions),
            censor_defaults_path=self.censor_defaults_path,
            exclusions_defaults_path=self.exclusions_defaults_path,
            overrides_path=self.path,
            overrides_count=0,
            seeded_from_default_version=seeded_from_default_version,
        )
        self._write_payload(self.path, self._payload(policy))

    @staticmethod
    def _payload(policy: ProfanityPolicy) -> dict[str, object]:
        return {
            "schema_version": policy.schema_version,
            "seeded_from_default_version": policy.seeded_from_default_version,
            "words": sorted(policy.censor_words),
            "exclusions": sorted(policy.exclusions),
        }

    def _write_payload(self, path: Path, payload: dict[str, object]) -> None:
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

            self._read_dictionary(temporary_path)
            os.replace(temporary_path, path)
            temporary_path = None
        except PolicyFileError:
            raise
        except OSError as exc:
            raise PolicyFileError(path, str(exc)) from exc
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
