"""Report the installed processing dependency graph for a target Windows Python.

This is evidence about the current environment, not a wheel lock: installed
metadata does not identify the original wheel URL or archive SHA-256.
"""

from __future__ import annotations

import argparse
import importlib.metadata as metadata
import json
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.tags import compatible_tags, cpython_tags, parse_tag
from packaging.utils import canonicalize_name


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
NATIVE_SUFFIXES = (".dll", ".pyd", ".exe")
NOTICE_MARKERS = ("license", "licence", "copying", "notice", "copyright")


def _target_environment(python_version: str) -> dict[str, str]:
    major, minor = python_version.split(".", 1)
    if not major.isdigit() or not minor.isdigit():
        raise ValueError("--python-version must be MAJOR.MINOR")
    environment = default_environment()
    environment.update(
        python_version=python_version,
        python_full_version=f"{python_version}.0",
        sys_platform="win32",
        os_name="nt",
        platform_system="Windows",
        platform_machine="AMD64",
        implementation_name="cpython",
        extra="",
    )
    return environment


def inspect(python_version: str) -> dict[str, object]:
    environment = _target_environment(python_version)
    target_version = tuple(int(part) for part in python_version.split("."))
    target_tags = set(cpython_tags(python_version=target_version, abis=[f"cp{target_version[0]}{target_version[1]}"], platforms=["win_amd64"]))
    target_tags.update(compatible_tags(python_version=target_version, interpreter=f"cp{target_version[0]}{target_version[1]}", platforms=["win_amd64"]))
    roots = [
        Requirement(line)
        for line in (REPOSITORY_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    pending = list(roots)
    visited: set[str] = set()
    constraints: dict[str, list[str]] = {}
    packages: list[dict[str, object]] = []
    while pending:
        requirement = pending.pop(0)
        name = canonicalize_name(requirement.name)
        constraints.setdefault(name, []).append(str(requirement))
        if name in visited:
            continue
        visited.add(name)
        try:
            distribution = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            packages.append({"name": name, "status": "not installed", "required_by": str(requirement)})
            continue

        version = distribution.version
        dependencies = []
        for raw in distribution.requires or ():
            child = Requirement(raw)
            if child.marker is None or child.marker.evaluate(environment):
                dependencies.append(str(child))
                pending.append(child)

        files = [str(item).replace("\\", "/") for item in distribution.files or ()]
        wheel_metadata = distribution.read_text("WHEEL") or ""
        wheel_tags = [line.removeprefix("Tag: ") for line in wheel_metadata.splitlines() if line.startswith("Tag: ")]
        installed_tags = {tag for wheel_tag in wheel_tags for tag in parse_tag(wheel_tag)}
        packages.append(
            {
                "name": name,
                "version": version,
                "status": "checked below",
                "requires_python": distribution.metadata.get("Requires-Python"),
                "license_metadata": distribution.metadata.get("License-Expression")
                or distribution.metadata.get("License")
                or "not declared",
                "wheel_tags": wheel_tags,
                "installed_wheel_compatible_with_target": bool(installed_tags & target_tags),
                "dependencies": sorted(dependencies),
                "native_files": sorted(item for item in files if item.lower().endswith(NATIVE_SUFFIXES) and not item.startswith("../")),
                "notice_files": sorted(item for item in files if any(marker in Path(item).name.lower() for marker in NOTICE_MARKERS)),
            }
        )
    for package in packages:
        name = str(package["name"])
        package["constraints"] = sorted(set(constraints[name]))
        if "version" in package:
            package["status"] = (
                "satisfies constraints"
                if all(str(package["version"]) in Requirement(item).specifier for item in constraints[name])
                else "version mismatch"
            )
    return {
        "target": f"CPython {python_version} Windows x64",
        "warning": "Installed metadata is not proof of the original wheel, archive hash, or target-Python import compatibility.",
        "packages": sorted(packages, key=lambda item: str(item["name"])),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-version", default="3.13")
    args = parser.parse_args()
    print(json.dumps(inspect(args.python_version), indent=2))


if __name__ == "__main__":
    main()
