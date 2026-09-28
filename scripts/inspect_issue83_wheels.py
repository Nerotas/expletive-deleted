"""Inspect exact PyPI Windows wheels for the local processing dependency versions.

Downloads are opt-in and go only to an ignored scratch wheelhouse. The output
is candidate evidence; it must be reviewed before becoming a release lock.
"""

from __future__ import annotations

import argparse
import email
import hashlib
import json
from pathlib import Path
import urllib.parse
import urllib.request
import zipfile

from packaging.requirements import Requirement
from packaging.tags import compatible_tags, cpython_tags
from packaging.utils import parse_wheel_filename

# Support both `python scripts/...py` and imports from focused unit tests.
if __package__:
    from .inspect_installed_dependencies import REPOSITORY_ROOT, _target_environment, inspect
else:
    from inspect_installed_dependencies import REPOSITORY_ROOT, _target_environment, inspect


def _fetch_json(opener: urllib.request.OpenerDirector, url: str) -> dict:
    with opener.open(url, timeout=40) as response:
        return json.load(response)


def _download(
    opener: urllib.request.OpenerDirector,
    url: str,
    destination: Path,
    expected_sha256: str,
) -> None:
    if destination.is_file():
        actual = hashlib.file_digest(destination.open("rb"), "sha256").hexdigest()
        if actual != expected_sha256:
            raise ValueError(f"Existing wheel hash mismatch: {destination.name}")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".partial")
    if partial.exists():
        raise FileExistsError(f"Inspect prior incomplete download before retrying: {partial}")
    digest = hashlib.sha256()
    try:
        with opener.open(url, timeout=80) as response, partial.open("xb") as output:
            while block := response.read(1024 * 1024):
                output.write(block)
                digest.update(block)
        if digest.hexdigest() != expected_sha256:
            raise ValueError(f"Downloaded wheel hash mismatch: {destination.name}")
        partial.replace(destination)
    except Exception:
        if partial.exists():
            partial.unlink()
        raise


def _inspect_archive(archive: Path, environment: dict[str, str]) -> dict:
    with zipfile.ZipFile(archive) as wheel:
        names = wheel.namelist()
        metadata_paths = [name for name in names if name.count("/") == 1 and name.endswith(".dist-info/METADATA")]
        if len(metadata_paths) != 1:
            raise ValueError(f"Expected one wheel METADATA file: {archive.name}")
        headers = email.message_from_bytes(wheel.read(metadata_paths[0]))
        dependencies = []
        for raw in headers.get_all("Requires-Dist", []):
            requirement = Requirement(raw)
            if requirement.marker is None or requirement.marker.evaluate(environment):
                dependencies.append(str(requirement))
        native = sorted(name for name in names if name.lower().endswith((".dll", ".pyd", ".exe")))
        notices = sorted(
            name
            for name in names
            if not name.endswith("/")
            and any(
                key in Path(name).name.lower()
                for key in ("license", "licence", "copying", "notice", "copyright")
            )
        )
        return {
            "license_metadata": headers.get("License-Expression") or headers.get("License") or "not declared",
            "requires_python": headers.get("Requires-Python"),
            "dependencies": sorted(dependencies),
            "native_files": native,
            "notice_files": notices,
        }


def inspect_wheels(python_version: str, wheelhouse: Path, download: bool) -> dict:
    local = inspect(python_version)
    target_version = tuple(int(part) for part in python_version.split("."))
    target_tags = list(cpython_tags(python_version=target_version, abis=[f"cp{target_version[0]}{target_version[1]}"], platforms=["win_amd64"]))
    target_tags.extend(compatible_tags(python_version=target_version, interpreter=f"cp{target_version[0]}{target_version[1]}", platforms=["win_amd64"]))
    tag_rank = {tag: index for index, tag in enumerate(target_tags)}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    environment = _target_environment(python_version)
    records = []
    for package in local["packages"]:
        if "version" not in package:
            raise ValueError(f"Local dependency is missing: {package['name']}")
        name, version = package["name"], package["version"]
        release_url = f"https://pypi.org/pypi/{urllib.parse.quote(str(name))}/{urllib.parse.quote(str(version))}/json"
        release = _fetch_json(opener, release_url)
        wheels = []
        for artifact in release["urls"]:
            if artifact["packagetype"] != "bdist_wheel" or artifact.get("yanked"):
                continue
            _parsed_name, _parsed_version, _build, tags = parse_wheel_filename(artifact["filename"])
            matching = tags & tag_rank.keys()
            if matching:
                wheels.append((min(tag_rank[tag] for tag in matching), artifact))
        if not wheels:
            raise ValueError(f"No Windows x64 CPython {python_version} wheel: {name}=={version}")
        selected = min(wheels, key=lambda item: (item[0], item[1]["filename"]))[1]
        sources = [item for item in release["urls"] if item["packagetype"] == "sdist" and not item.get("yanked")]
        archive = wheelhouse / selected["filename"]
        if download:
            _download(opener, selected["url"], archive, selected["digests"]["sha256"])
        elif archive.is_file():
            with archive.open("rb") as source:
                actual = hashlib.file_digest(source, "sha256").hexdigest()
            if actual != selected["digests"]["sha256"]:
                raise ValueError(f"Cached wheel hash mismatch: {archive.name}")
        record = {
            "name": name,
            "version": version,
            "wheel": selected["filename"],
            "wheel_url": selected["url"],
            "wheel_sha256": selected["digests"]["sha256"],
            "source": [
                {"filename": item["filename"], "url": item["url"], "sha256": item["digests"]["sha256"]}
                for item in sources
            ],
            "inspection": _inspect_archive(archive, environment) if archive.is_file() else None,
        }
        records.append(record)
        print(f"{name}=={version}: {selected['filename']} ({'inspected' if record['inspection'] else 'metadata only'})", flush=True)
    selected_names = {str(record["name"]) for record in records}
    missing_edges = sorted({
        str(Requirement(raw).name).lower().replace("_", "-")
        for record in records
        for raw in (record["inspection"] or {}).get("dependencies", [])
        if str(Requirement(raw).name).lower().replace("_", "-") not in selected_names
    })
    return {
        "target": local["target"],
        "status": "candidate; not approved for release",
        "missing_dependency_edges": missing_edges,
        "packages": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-version", default="3.13")
    parser.add_argument("--wheelhouse", type=Path, default=REPOSITORY_ROOT / "tmp" / "issue83-artifacts" / "wheels")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print the complete candidate manifest after progress lines")
    args = parser.parse_args()
    result = inspect_wheels(args.python_version, args.wheelhouse, args.download)
    print(f"Inspected {sum(item['inspection'] is not None for item in result['packages'])}/{len(result['packages'])} wheels; missing edges: {result['missing_dependency_edges']}")
    if args.json:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
