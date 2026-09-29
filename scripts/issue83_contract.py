"""Fail-closed Phase 2 contracts for a future Issue 83 Windows runtime.

This deliberately does not read the Phase 1 candidate manifests or change the
current Python-only packaging flow. An input lock must explicitly be approved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse


SHA256 = re.compile(r"^[0-9a-f]{64}$")
IDENTIFIER = re.compile(r"^[a-z][a-z0-9-]*$")
ARTIFACT_KINDS = {"payload", "source", "patch", "build-script", "notice", "license"}
TRANSFORM_KINDS = {"copy", "extract", "install", "build", "generate"}
SCOPES = {"installer", "source"}
WINDOWS_DEVICE = re.compile(r"^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?$", re.IGNORECASE)


class ContractError(ValueError):
    """The input lock, inventory, or staged files violate the contract."""


def _error(message: str) -> None:
    raise ContractError(message)


def _exact_keys(value: object, required: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != required:
        _error(f"{label} must have exactly these fields: {', '.join(sorted(required))}")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        _error(f"{label} must be a nonempty trimmed string")
    return value


def _identifier(value: object, label: str) -> str:
    result = _string(value, label)
    if not IDENTIFIER.fullmatch(result):
        _error(f"{label} must be a lowercase hyphenated identifier")
    return result


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        _error(f"{label} must be a lowercase SHA-256 digest")
    return value


def _path(value: object, label: str) -> str:
    result = _string(value, label)
    # Paths are portable POSIX-relative names, never absolute Windows paths or
    # traversal segments; the tree audit separately rejects symlinks.
    segments = result.split("/")
    if (
        result.startswith("/")
        or any(character in result for character in '\\:<>"|?*')
        or any(ord(character) < 32 for character in result)
        or any(part in {"", ".", ".."} or part.endswith((".", " ")) or WINDOWS_DEVICE.fullmatch(part) for part in segments)
    ):
        _error(f"{label} must be a safe relative Windows/POSIX path")
    return result


def _list(value: object, label: str) -> list:
    if not isinstance(value, list) or not value:
        _error(f"{label} must be a nonempty array")
    return value


def _ids(value: object, label: str) -> list[str]:
    ids = [_identifier(item, label) for item in _list(value, label)]
    if len(ids) != len(set(ids)):
        _error(f"{label} repeats an identifier")
    return ids


def _unique_json(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            _error(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_json(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_json)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"invalid UTF-8 JSON: {path}") from exc
    if not isinstance(value, dict):
        _error(f"JSON root must be an object: {path}")
    return value, raw


def validate_input_lock(lock: dict) -> tuple[dict[str, dict], dict[str, dict]]:
    _exact_keys(lock, {"schema_version", "status", "release_id", "platform", "components", "transformations"}, "input lock")
    if type(lock["schema_version"]) is not int or lock["schema_version"] != 1 or lock["status"] != "approved" or lock["platform"] != "win32-x64":
        _error("input lock must be schema v1, approved, and win32-x64")
    _identifier(lock["release_id"], "release_id")
    components: dict[str, dict] = {}
    artifacts: dict[str, dict] = {}
    for component in _list(lock["components"], "components"):
        _exact_keys(component, {"id", "version", "license_expression", "artifacts", "source_artifact_ids", "notice_artifact_ids", "license_artifact_ids"}, "component")
        component_id = _identifier(component["id"], "component.id")
        if component_id in components or component_id == "release":
            _error(f"duplicate/reserved component id: {component_id}")
        _string(component["version"], f"{component_id}.version")
        _string(component["license_expression"], f"{component_id}.license_expression")
        components[component_id] = component
        for artifact in _list(component["artifacts"], f"{component_id}.artifacts"):
            base_fields = {"id", "kind", "name", "url", "sha256"}
            embedded_fields = {"origin_artifact_id", "archive_member"}
            if not isinstance(artifact, dict) or set(artifact) not in (base_fields, base_fields | embedded_fields):
                _error("artifact must have the base fields and either both or neither embedded-origin fields")
            artifact_id = _identifier(artifact["id"], "artifact.id")
            if artifact_id in artifacts:
                _error(f"duplicate artifact id: {artifact_id}")
            if artifact["kind"] not in ARTIFACT_KINDS:
                _error(f"invalid artifact kind: {artifact_id}")
            name = _path(artifact["name"], f"{artifact_id}.name")
            if "/" in name:
                _error(f"artifact name must be a filename: {artifact_id}")
            url = urlparse(_string(artifact["url"], f"{artifact_id}.url"))
            if url.scheme != "https" or not url.netloc or url.username or url.password:
                _error(f"artifact origin must be an HTTPS URL: {artifact_id}")
            _sha(artifact["sha256"], f"{artifact_id}.sha256")
            artifacts[artifact_id] = {**artifact, "owner": component_id}
        for artifact in component["artifacts"]:
            if "origin_artifact_id" in artifact:
                artifact_id = artifact["id"]
                origin_id = _identifier(artifact["origin_artifact_id"], f"{artifact_id}.origin_artifact_id")
                origin = artifacts.get(origin_id)
                if (
                    origin is None
                    or origin["owner"] != component_id
                    or origin["kind"] not in {"payload", "source"}
                    or "origin_artifact_id" in origin
                    or artifact["url"] != origin["url"]
                ):
                    _error(f"embedded artifact needs a direct same-component archive origin: {artifact_id}")
                _path(artifact["archive_member"], f"{artifact_id}.archive_member")
        if not any(item["kind"] == "payload" for item in component["artifacts"]):
            _error(f"component has no selected payload: {component_id}")
        for field, kind in (("source_artifact_ids", "source"), ("notice_artifact_ids", "notice"), ("license_artifact_ids", "license")):
            for artifact_id in _ids(component[field], f"{component_id}.{field}"):
                if artifacts.get(artifact_id, {}).get("owner") != component_id or artifacts[artifact_id]["kind"] != kind:
                    _error(f"{component_id}.{field} refers to a missing or wrong-kind artifact: {artifact_id}")

    transformations: dict[str, dict] = {}
    for transformation in _list(lock["transformations"], "transformations"):
        _exact_keys(transformation, {"id", "kind", "input_artifact_ids"}, "transformation")
        transformation_id = _identifier(transformation["id"], "transformation.id")
        if transformation_id in transformations or transformation["kind"] not in TRANSFORM_KINDS:
            _error(f"duplicate or invalid transformation: {transformation_id}")
        inputs = _ids(transformation["input_artifact_ids"], f"{transformation_id}.input_artifact_ids")
        if any(item not in artifacts for item in inputs):
            _error(f"transformation uses unknown artifact: {transformation_id}")
        if transformation["kind"] == "build" and not {"source", "build-script"}.issubset({artifacts[item]["kind"] for item in inputs}):
            _error(f"build requires source and build-script artifacts: {transformation_id}")
        transformations[transformation_id] = transformation
    return artifacts, transformations


def validate_inventory(lock: dict, lock_bytes: bytes, inventory: dict) -> None:
    artifacts, transformations = validate_input_lock(lock)
    _exact_keys(inventory, {"schema_version", "release_id", "platform", "input_lock_sha256", "files"}, "inventory")
    if type(inventory["schema_version"]) is not int or inventory["schema_version"] != 1 or inventory["release_id"] != lock["release_id"] or inventory["platform"] != lock["platform"]:
        _error("inventory identity does not match input lock")
    if _sha(inventory["input_lock_sha256"], "input_lock_sha256") != hashlib.sha256(lock_bytes).hexdigest():
        _error("inventory references a different input lock")
    seen_paths: set[tuple[str, str]] = set()
    supplied: set[tuple[str, str]] = set()
    payload_owners: set[str] = set()
    for file in _list(inventory["files"], "files"):
        _exact_keys(file, {"scope", "path", "sha256", "purpose", "owner_component_id", "transformation_id", "derived_from"}, "inventory file")
        scope = _string(file["scope"], "inventory file.scope")
        if scope not in SCOPES:
            _error(f"invalid inventory scope: {scope}")
        relative = _path(file["path"], "inventory file.path")
        key = (scope, relative.casefold())  # Windows paths are case-insensitive.
        if key in seen_paths:
            _error(f"duplicate inventory path: {scope}/{relative}")
        seen_paths.add(key)
        _sha(file["sha256"], f"{scope}/{relative}.sha256")
        purpose = _string(file["purpose"], f"{scope}/{relative}.purpose")
        allowed = {"payload", "notice", "license", "metadata"} if scope == "installer" else {"source", "patch", "build-script"}
        if purpose not in allowed:
            _error(f"invalid purpose for {scope}/{relative}: {purpose}")
        owner = _string(file["owner_component_id"], f"{scope}/{relative}.owner_component_id")
        if owner != "release" and owner not in {component["id"] for component in lock["components"]}:
            _error(f"unknown inventory owner: {owner}")
        transformation = transformations.get(_identifier(file["transformation_id"], f"{scope}/{relative}.transformation_id"))
        if transformation is None:
            _error(f"unknown transformation for {scope}/{relative}")
        inputs = _ids(file["derived_from"], f"{scope}/{relative}.derived_from")
        if set(inputs) != set(transformation["input_artifact_ids"]):
            _error(f"file does not match transformation inputs: {scope}/{relative}")
        if owner == "release":
            if purpose != "metadata" or transformation["kind"] != "generate":
                _error(f"release-owned file must be generated metadata: {scope}/{relative}")
        elif any(artifacts[item]["owner"] != owner for item in inputs):
            _error(f"cross-component transformation ownership: {scope}/{relative}")
        if purpose in {"source", "patch", "build-script", "notice", "license"}:
            if not any(artifacts[item]["kind"] == purpose for item in inputs):
                _error(f"missing matching {purpose} input: {scope}/{relative}")
            supplied.update((scope, item) for item in inputs if artifacts[item]["kind"] == purpose)
        if purpose == "payload" and any(artifacts[item]["kind"] == "payload" for item in inputs):
            payload_owners.add(owner)
        if transformation["kind"] == "copy" and len(inputs) == 1 and purpose == artifacts[inputs[0]]["kind"]:
            if file["sha256"] != artifacts[inputs[0]]["sha256"]:
                _error(f"copied artifact hash does not match input lock: {scope}/{relative}")

    for component in lock["components"]:
        if component["id"] not in payload_owners:
            _error(f"component payload is absent from installer: {component['id']}")
        for field, scope in (("source_artifact_ids", "source"), ("notice_artifact_ids", "installer"), ("license_artifact_ids", "installer")):
            for artifact_id in component[field]:
                if (scope, artifact_id) not in supplied:
                    _error(f"required {field} artifact is absent from {scope}: {artifact_id}")
        for artifact in component["artifacts"]:
            if artifact["kind"] in {"patch", "build-script"} and ("source", artifact["id"]) not in supplied:
                _error(f"build material is absent from source companion: {artifact['id']}")


def _is_link_or_junction(entry: Path) -> bool:
    # is_junction is available only on newer Python; keep the validator usable
    # on the repository's older supported development Pythons.
    is_junction = getattr(entry, "is_junction", lambda: False)
    return entry.is_symlink() or is_junction()


def validate_trees(inventory: dict, installer_root: Path, source_root: Path) -> None:
    expected = {(item["scope"], item["path"].casefold()): item for item in inventory["files"]}
    actual: set[tuple[str, str]] = set()
    for scope, root in (("installer", installer_root), ("source", source_root)):
        if not root.is_dir() or _is_link_or_junction(root):
            _error(f"{scope} root must be a real directory: {root}")
        for entry in root.rglob("*"):
            relative = entry.relative_to(root).as_posix()
            if _is_link_or_junction(entry):
                _error(f"symlink or junction is not allowed: {scope}/{relative}")
            if entry.is_dir():
                continue
            if not entry.is_file():
                _error(f"unsupported entry: {scope}/{relative}")
            key = (scope, relative.casefold())
            if key in actual:
                _error(f"case-colliding file: {scope}/{relative}")
            actual.add(key)
            record = expected.get(key)
            if record is None:
                _error(f"undeclared file: {scope}/{relative}")
            digest_state = hashlib.sha256()
            with entry.open("rb") as stream:
                while block := stream.read(1024 * 1024):
                    digest_state.update(block)
            digest = digest_state.hexdigest()
            if digest != record["sha256"]:
                _error(f"file hash mismatch: {scope}/{relative}")
    missing = expected.keys() - actual
    if missing:
        scope, relative = sorted(missing)[0]
        _error(f"declared file is absent: {scope}/{relative}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-lock", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--installer-root", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    args = parser.parse_args()
    lock, raw = _read_json(args.input_lock)
    inventory, _ = _read_json(args.inventory)
    validate_inventory(lock, raw, inventory)
    validate_trees(inventory, args.installer_root, args.source_root)
    print(f"Issue 83 contract passed: {lock['release_id']}")


if __name__ == "__main__":
    main()
