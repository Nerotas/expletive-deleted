"""Atomic persistence for user profanity-policy overrides."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from backend.runtime import (
    get_profanity_censor_words_file,
    get_profanity_exclusions_file,
    load_profanity_censor_words,
    load_profanity_exclusions,
    normalize_policy_word,
)
from backend.application_identity import prepare_app_data_root


POLICY_SCHEMA_VERSION = 1
PolicyTarget = Literal["censor", "exclude"]
PolicyAction = Literal["add", "remove"]
PolicyClassification = Literal["censor", "exclude", "none"]


class PolicyFileError(RuntimeError):
    """Raised when the local user policy cannot be safely read or written."""

    def __init__(self, path: Path, detail: str):
        self.path = path
        self.detail = detail
        super().__init__(f"Policy file {path}: {detail}")


@dataclass(frozen=True)
class ProfanityPolicy:
    censor_words: frozenset[str]
    exclusions: frozenset[str]
    censor_defaults_path: Path
    exclusions_defaults_path: Path
    overrides_path: Path
    overrides_count: int

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
    return prepare_app_data_root(environment, home) / "policy.json"


class PolicyStore:
    """Combine immutable shipped defaults with a small user-owned override map."""

    def __init__(
        self,
        path: Path | None = None,
        *,
        censor_defaults_path: Path | None = None,
        exclusions_defaults_path: Path | None = None,
    ):
        self.path = (path or default_policy_path()).expanduser().resolve()
        self.censor_defaults_path = (
            censor_defaults_path or get_profanity_censor_words_file()
        ).expanduser().resolve()
        self.exclusions_defaults_path = (
            exclusions_defaults_path or get_profanity_exclusions_file()
        ).expanduser().resolve()

    def load(self) -> ProfanityPolicy:
        censor_defaults = load_profanity_censor_words(self.censor_defaults_path)
        exclusion_defaults = load_profanity_exclusions(self.exclusions_defaults_path)
        overrides = self._read_overrides()
        censor_words, exclusions = self._materialize(
            censor_defaults,
            exclusion_defaults,
            overrides,
        )
        return ProfanityPolicy(
            censor_words=frozenset(censor_words),
            exclusions=frozenset(exclusions),
            censor_defaults_path=self.censor_defaults_path,
            exclusions_defaults_path=self.exclusions_defaults_path,
            overrides_path=self.path,
            overrides_count=len(overrides),
        )

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
        changed = before.classification(word) != desired
        if not changed:
            return before, False

        censor_defaults = load_profanity_censor_words(self.censor_defaults_path)
        exclusion_defaults = load_profanity_exclusions(self.exclusions_defaults_path)
        overrides = self._read_overrides()
        baseline = self._baseline_classification(word, censor_defaults, exclusion_defaults)

        # Matching the baseline needs no override. "none" is a tombstone that
        # keeps an intentional removal stable across future default-list updates.
        if action == "remove":
            overrides[word] = "none"
        elif desired == baseline:
            overrides.pop(word, None)
        else:
            overrides[word] = desired
        self._write_overrides(overrides)
        return self.load(), True

    @staticmethod
    def _baseline_classification(
        word: str,
        censor_defaults: set[str],
        exclusion_defaults: set[str],
    ) -> PolicyTarget | None:
        if word in exclusion_defaults:
            return "exclude"
        if word in censor_defaults:
            return "censor"
        return None

    @staticmethod
    def _materialize(
        censor_defaults: set[str],
        exclusion_defaults: set[str],
        overrides: dict[str, PolicyClassification],
    ) -> tuple[set[str], set[str]]:
        exclusions = set(exclusion_defaults)
        censor_words = set(censor_defaults) - exclusions
        for word, classification in overrides.items():
            censor_words.discard(word)
            exclusions.discard(word)
            if classification == "censor":
                censor_words.add(word)
            elif classification == "exclude":
                exclusions.add(word)
        return censor_words, exclusions

    def _read_overrides(self) -> dict[str, PolicyClassification]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise PolicyFileError(
                self.path,
                f"invalid JSON at line {exc.lineno}, column {exc.colno}",
            ) from exc
        except OSError as exc:
            raise PolicyFileError(self.path, str(exc)) from exc

        if not isinstance(payload, dict) or set(payload) != {"schema_version", "overrides"}:
            raise PolicyFileError(
                self.path,
                "must contain only schema_version and overrides",
            )
        if (
            isinstance(payload["schema_version"], bool)
            or not isinstance(payload["schema_version"], int)
            or payload["schema_version"] != POLICY_SCHEMA_VERSION
        ):
            raise PolicyFileError(
                self.path,
                f"unsupported schema version {payload['schema_version']!r}",
            )
        raw_overrides = payload["overrides"]
        if not isinstance(raw_overrides, dict):
            raise PolicyFileError(self.path, "overrides must be an object")

        overrides: dict[str, PolicyClassification] = {}
        for raw_word, classification in raw_overrides.items():
            if not isinstance(raw_word, str) or classification not in (
                "censor",
                "exclude",
                "none",
            ):
                raise PolicyFileError(self.path, "contains an invalid word classification")
            try:
                word = normalize_policy_word(raw_word)
            except ValueError as exc:
                raise PolicyFileError(self.path, str(exc)) from exc
            if word != raw_word:
                raise PolicyFileError(self.path, f"contains a non-normalized word: {raw_word!r}")
            overrides[word] = classification
        return overrides

    def _write_overrides(self, overrides: dict[str, PolicyClassification]) -> None:
        temporary_path: Path | None = None
        payload = {
            "schema_version": POLICY_SCHEMA_VERSION,
            "overrides": dict(sorted(overrides.items())),
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                json.dump(payload, temporary_file, indent=2, sort_keys=True)
                temporary_file.write("\n")
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
                temporary_path = Path(temporary_file.name)

            # Validate the staged document before it can replace a valid policy.
            staged_store = PolicyStore(
                temporary_path,
                censor_defaults_path=self.censor_defaults_path,
                exclusions_defaults_path=self.exclusions_defaults_path,
            )
            if staged_store._read_overrides() != overrides:
                raise PolicyFileError(self.path, "staged policy verification failed")
            os.replace(temporary_path, self.path)
            temporary_path = None
        except PolicyFileError:
            raise
        except OSError as exc:
            raise PolicyFileError(self.path, str(exc)) from exc
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
