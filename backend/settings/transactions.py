"""Field-level optimistic settings transactions, shared by desktop and CLI."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy

from .models import SettingsValidationError
from .serialization import settings_from_dict, settings_to_dict


def snapshot(settings):
    payload = settings_to_dict(settings)
    revision = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"settings": payload, "revision": revision}


def fields(payload):
    return {f"{group}.{key}": value for group, values in payload.items()
            if isinstance(values, dict) for key, value in values.items()}


def changes_between(base, draft):
    # Validate complete drafts before deriving intent; schema edits are never patches.
    parsed = settings_to_dict(settings_from_dict(draft))
    before = fields(base)
    return [{"field": field, "expected": before[field], "value": value}
            for field, value in fields(parsed).items() if before[field] != value]


def validate_base(base):
    if not isinstance(base, dict) or set(base) != {"settings", "revision"}:
        raise ValueError("A settings snapshot and revision are required")
    if snapshot(settings_from_dict(base["settings"])) != base:
        raise ValueError("The settings baseline does not match its revision")
    return base


def transact(store, revision, changes, *, effective=None, prepare=None, strict=False):
    if not isinstance(revision, str) or not revision or not isinstance(changes, list):
        raise ValueError("A settings revision and field changes are required")
    with store.locked():
        persisted = store.load()
        current = effective(persisted) if effective else persisted
        latest = snapshot(current)
        current_fields = fields(latest["settings"])
        saved_fields = fields(settings_to_dict(persisted))
        merged = deepcopy(settings_to_dict(persisted))
        conflicts, seen = [], set()
        for change in changes:
            if not isinstance(change, dict) or set(change) != {"field", "expected", "value"}:
                raise ValueError("Each settings change needs field, expected, and value")
            field = change["field"]
            if not isinstance(field, str) or field not in current_fields or field in seen:
                raise ValueError("Unknown or duplicate settings field")
            seen.add(field)
            expected, proposed, value = change["expected"], change["value"], current_fields[field]
            group, key = field.split(".")
            for candidate in (expected, proposed):
                valid_type = (candidate is None or isinstance(candidate, str)) if group == "runtime" else type(candidate) is type(value)
                if not valid_type:
                    raise SettingsValidationError([f"{field} has an invalid value type"])
            if value != saved_fields[field] and proposed != value:
                raise SettingsValidationError([f"{field} is controlled by a runtime override; remove the override before editing it"])
            if (strict and revision != latest["revision"]) or (value != expected and value != proposed):
                conflicts.append({"field": field, "expected": expected, "current": value, "proposed": proposed})
            if value == saved_fields[field]:
                merged[group][key] = proposed
        # Validate all proposals together: coordinated directory changes may be valid
        # even when either individual change would collide with an old directory.
        updated = settings_from_dict(merged, persisted)
        canonical = fields(settings_to_dict(updated))
        for change in changes:
            if current_fields[change["field"]] == saved_fields[change["field"]] and canonical[change["field"]] != change["value"]:
                raise SettingsValidationError([f'{change["field"]} must use its canonical value'])
        if conflicts:
            return {"status": "conflict", "snapshot": latest, "conflicts": conflicts}
        if prepare:
            updated = prepare(updated)
        store.save(updated)
        return {"status": "saved", "snapshot": snapshot(effective(updated) if effective else updated), "conflicts": []}
