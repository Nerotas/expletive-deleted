"""Inspect exact upstream release assets proposed for Issue 83 Phase 1A.

The chosen FFmpeg release is a candidate until its build and source mapping is
verified. Downloads, when requested, stay in ignored repository scratch space.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RELEASES = (
    ("actions/python-versions", "3.13.15-31064747964", ("python-3.13.15-win32-x64.zip",)),
    ("BtbN/FFmpeg-Builds", "autobuild-2026-09-27-13-04", ("ffmpeg-n9.0.2-12-gc867e13549-win64-gpl-9.0.zip",)),
    ("yt-dlp/yt-dlp", "2026.08.19", ("yt-dlp.exe", "yt-dlp.tar.gz", "SHA2-256SUMS", "SHA2-256SUMS.sig")),
    ("denoland/deno", "v2.9.6", ("deno-x86_64-pc-windows-msvc.zip", "deno-x86_64-pc-windows-msvc.zip.sha256sum")),
)


def _read_json(opener: urllib.request.OpenerDirector, url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "ExpletiveDeleted-Issue83-Research"})
    with opener.open(request, timeout=40) as response:
        return json.load(response)


def _download(opener: urllib.request.OpenerDirector, url: str, destination: Path, expected: str | None) -> str:
    if destination.exists():
        with destination.open("rb") as source:
            actual = hashlib.file_digest(source, "sha256").hexdigest()
        if expected and actual != expected:
            raise ValueError(f"Cached artifact hash mismatch: {destination}")
        return actual
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".partial")
    if partial.exists():
        raise FileExistsError(f"Inspect prior incomplete download: {partial}")
    digest = hashlib.sha256()
    try:
        with opener.open(url, timeout=90) as response, partial.open("xb") as output:
            while block := response.read(1024 * 1024):
                output.write(block)
                digest.update(block)
        actual = digest.hexdigest()
        if expected and actual != expected:
            raise ValueError(f"Downloaded artifact hash mismatch: {destination.name}")
        partial.replace(destination)
        return actual
    except Exception:
        if partial.exists():
            partial.unlink()
        raise


def inspect_releases(directory: Path, download: bool) -> list[dict]:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    findings = []
    for repository, tag, names in RELEASES:
        release = _read_json(opener, f"https://api.github.com/repos/{repository}/releases/tags/{tag}")
        assets = {asset["name"]: asset for asset in release["assets"]}
        for name in names:
            if name not in assets:
                raise ValueError(f"Release asset is absent: {repository} {tag} {name}")
            asset = assets[name]
            publisher_digest = asset.get("digest") or ""
            expected = publisher_digest.removeprefix("sha256:") if publisher_digest.startswith("sha256:") else None
            archive = directory / repository.replace("/", "-") / tag / name
            actual = _download(opener, asset["browser_download_url"], archive, expected) if download else None
            archive_entries = None
            if actual and name.lower().endswith(".zip"):
                with zipfile.ZipFile(archive) as bundle:
                    archive_entries = bundle.namelist()
            findings.append({
                "repository": repository,
                "tag": tag,
                "name": name,
                "url": asset["browser_download_url"],
                "size": asset["size"],
                "publisher_digest": publisher_digest or None,
                "downloaded_sha256": actual,
                "archive_entries": archive_entries,
            })
            print(f"{repository}@{tag}: {name} digest={publisher_digest or 'absent'} downloaded={bool(actual)}", flush=True)
    return findings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=REPOSITORY_ROOT / "tmp" / "issue83-artifacts" / "tools")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    findings = inspect_releases(args.directory, args.download)
    if args.json:
        print(json.dumps(findings, indent=2))


if __name__ == "__main__":
    main()
