# Windows x64 private Python contract

This directory records the only third-party runtime included with the Windows
installer. Generated binaries remain ignored by Git.

The release payload contains:

```text
python/python.exe
THIRD_PARTY_NOTICES.md
LICENSES/
sbom.cdx.json
runtime-manifest.json
```

The private Python directory includes the standard library and the installed,
pinned `pip`, which is the bootstrap used by the consent-driven first-run setup.
Assembly removes `Lib/test` and `Lib/ensurepip`: neither is needed at runtime,
and both can contain unaudited wheel fixtures or bootstrap wheels. The payload
must not contain the processing packages from `requirements.txt`,
FFmpeg/FFprobe, yt-dlp, Deno, or a Whisper model.

`runtime-manifest.json` conforms to `runtime-manifest.schema.json`. The release
builder copies the pinned Python runtime before installing development
dependencies, generates hashes for every shipped file, and runs both the static
audit and Windows executable verification before packaging.

Use `scripts/build-audited-runtime.ps1` to create the Python-only payload. The
script records Python and pip in the notices and SBOM, then delegates copying to
`scripts/assemble-bundled-runtime.ps1`. The audit rejects processing packages,
media executables, speech models, unrecorded files, and legacy all-in-one
runtime manifests.

After installation, onboarding can locate compatible existing components or,
after showing an exact plan and receiving approval, obtain the pinned Python
packages under `%LOCALAPPDATA%\ExpletiveDeleted\dependencies\python` and place
FFmpeg/FFprobe, yt-dlp, Deno, and the selected Whisper model elsewhere in the
per-user application-data runtime.
