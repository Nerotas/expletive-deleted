"""Local redo journal for the existing split dictionary formats.

The journal is the commit decision. After it is published, every reader finishes
that decision before exposing data. No journal-provided path is ever followed.
"""

from __future__ import annotations

import json
import os
import tempfile
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, TypeVar, cast
from uuid import UUID, uuid4

from backend.filesystem.locking import store_lock
from .errors import PolicyFileError, PolicyRecoveryError

if TYPE_CHECKING:
    from .store import PolicyStore

Method = TypeVar("Method", bound=Callable[..., Any])


STORE_NAMES = frozenset({"censored.json", "exclusions.json", "discovered.json"})
JOURNAL_NAME = ".policy-journal.json"
LOCK_NAME = ".policy.lock"


def sync_directory(directory: Path) -> None:
    # Windows fsync flushes each file; POSIX also needs directory entry durability.
    if os.name != "nt":
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def write_atomic(path: Path, payload: dict) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
        sync_directory(path.parent)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _validate(store: PolicyStore, journal: object) -> dict:
    if not isinstance(journal, dict) or set(journal) != {"version", "transaction_id", "stores"}:
        raise ValueError("invalid journal envelope")
    if type(journal["version"]) is not int or journal["version"] != 1:
        raise ValueError("invalid journal version")
    if not isinstance(journal["transaction_id"], str):
        raise ValueError("invalid transaction identifier")
    UUID(journal["transaction_id"])
    payloads = journal["stores"]
    if not isinstance(payloads, dict) or not payloads or not set(payloads) <= STORE_NAMES:
        raise ValueError("invalid journal destinations")
    # Validate the entire journal before publishing even the first destination.
    for name, payload in payloads.items():
        path = store.directory / name
        if path.is_symlink() or path.resolve() != path:
            raise ValueError("dictionary destination is redirected")
        store._validate_store_payload(path, payload)
    effective = dict(payloads)
    for name in STORE_NAMES - payloads.keys():
        path = store.directory / name
        if path.exists():
            effective[name] = store._read_json(path)
            store._validate_store_payload(path, effective[name])
    if {"censored.json", "exclusions.json"} <= effective.keys():
        censor = {entry["value"] for entry in effective["censored.json"]["entries"]}
        exclude = {entry["value"] for entry in effective["exclusions.json"]["entries"]}
        if censor & exclude:
            raise ValueError("contradictory classifications")
        if "discovered.json" in effective and (censor | exclude) & set(effective["discovered.json"]["words"]):
            raise ValueError("classified discovery entries")
    return payloads


def _publish(store: PolicyStore, payloads: dict) -> None:
    for name in sorted(payloads):
        write_atomic(store.directory / name, payloads[name])
    (store.directory / JOURNAL_NAME).unlink()
    sync_directory(store.directory)


def _unique_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate journal field")
        result[key] = value
    return result


def recover(store: PolicyStore) -> None:
    path = store.directory / JOURNAL_NAME
    if not os.path.lexists(path):
        return
    try:
        if path.is_symlink():
            raise ValueError("redirected journal")
        journal = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_keys)
        _publish(store, _validate(store, journal))
    except (OSError, ValueError, PolicyFileError) as exc:
        # Never include journal contents (potentially sensitive words) in errors.
        raise PolicyRecoveryError(path, "Recovery could not finish. Keep the dictionary files and "
                                  "journal intact, check folder access and free disk space, then retry. "
                                  "If this persists, restore a known-good backup with application support.") from exc


def transactional(method: Method) -> Method:
    @wraps(method)
    def wrapped(self: PolicyStore, *args: Any, **kwargs: Any) -> Any:
        try:
            with store_lock(self.directory / LOCK_NAME, self.lock_timeout):
                if self._pending is not None:
                    return method(self, *args, **kwargs)
                recover(self)
                self._pending = {}
                try:
                    result = method(self, *args, **kwargs)
                    if self._pending:
                        journal = {"version": 1, "transaction_id": str(uuid4()), "stores": self._pending}
                        _validate(self, journal)
                        write_atomic(self.directory / JOURNAL_NAME, journal)
                        try:
                            _publish(self, self._pending)
                        except OSError as exc:
                            raise PolicyRecoveryError(self.directory / JOURNAL_NAME,
                                "An update was interrupted and may have committed. Check folder access "
                                "and disk space, then reload to recover before retrying the edit.") from exc
                    return result
                finally:
                    self._pending = None
        except OSError as exc:
            raise PolicyFileError(self.directory, f"Could not access the dictionary: {exc}") from exc
    return cast(Method, wrapped)
