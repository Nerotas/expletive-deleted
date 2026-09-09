# Windows x64 bundled runtime staging directory

This directory is the local staging root for the audited Windows x64 processing runtime. Its generated payload is intentionally ignored by Git. The release build supplies it through `BUNDLED_RUNTIME_DIR` and validates it with `npm run audit:bundled-runtime` before Electron Builder includes it as `resources/app-runtime`.

The staged payload must contain:

```text
python/python.exe
ffmpeg/ffmpeg.exe
ffmpeg/ffprobe.exe
yt-dlp/yt-dlp.exe
THIRD_PARTY_NOTICES.md
LICENSES/
sbom.cdx.json
ffmpeg-source.zip
ffmpeg-build.json
runtime-manifest.json
```

`runtime-manifest.json` must conform to `runtime-manifest.schema.json`. The validator rejects Whisper models, `libx264`, `libx265`, GPL/nonfree FFmpeg configure flags, and an incomplete Python, FFmpeg, or yt-dlp runtime.

Do not place a Whisper model in this directory. The model remains a user-selected download. The pinned official yt-dlp Windows executable is bundled with the application.

## Approved build inputs

[`build-inputs.json`](build-inputs.json) locks the component versions and the FFmpeg configuration that a release builder must start from. It deliberately does not contain binaries or wheels. The normal PyAV Windows wheel and PyAV's ordinary `pyav-ffmpeg` output are disallowed because they include GPL x264/x265 libraries.

The release builder creates a private Python runtime, builds FFmpeg as LGPL-only shared libraries, builds PyAV against those same libraries, and adds the notices, SBOM, source archive, `ffmpeg-build.json`, and a metadata-complete `runtime-manifest.json`. `scripts/assemble-bundled-runtime.ps1` copies only these prebuilt, reviewed inputs into a new payload directory and refuses to overwrite an existing one; it does not compile or download third-party code. Run `npm run generate:bundled-manifest -- <runtime-directory>` after every final payload change. It hashes every shipped artifact and refreshes the FFmpeg source-archive record; it does not invent release metadata. Then run `npm run audit:bundled-runtime` and `npm run verify:bundled-runtime` on Windows before setting `BUNDLED_RUNTIME_DIR` for packaging. The executable verification imports the required packages, loads PyAV, checks both FFmpeg tools, and rejects GPL/nonfree configuration or libx264/libx265. `package:bundled-win` makes a missing runtime a hard error.
