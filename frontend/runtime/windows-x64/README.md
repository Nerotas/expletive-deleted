# Windows x64 runtime contract

This directory records the Windows x64 runtime contract. Development and
setup-first production builds obtain processing components into the per-user
application-data runtime root after explicit confirmation; generated binaries
are intentionally ignored by Git.

When a private Python payload is supplied to a production build, it may contain:

```text
python/python.exe
ffmpeg/ffmpeg.exe
ffmpeg/ffprobe.exe
yt-dlp/yt-dlp.exe
deno/deno.exe
THIRD_PARTY_NOTICES.md
LICENSES/
sbom.cdx.json
ffmpeg-source.zip
ffmpeg-build.json
runtime-manifest.json
```

`runtime-manifest.json` must conform to `runtime-manifest.schema.json` for any
audited runtime artifact. The application does not require FFmpeg, yt-dlp, or
Deno to be physically present at first launch; onboarding verifies or obtains
them before enabling the workflows that need them. Whisper models are never
part of the installer payload.

Do not place a Whisper model, yt-dlp executable, or Deno executable in this directory. The model, yt-dlp, and Deno remain user-approved onboarding downloads.

## Approved build inputs

[`build-inputs.json`](build-inputs.json) locks the component versions and the FFmpeg configuration that a release builder must start from. It deliberately does not contain binaries or wheels. The normal PyAV Windows wheel and PyAV's ordinary `pyav-ffmpeg` output are disallowed because they include GPL x264/x265 libraries.

The release builder creates a private Python runtime, builds FFmpeg as LGPL-only shared libraries, builds PyAV against those same libraries, and adds the notices, SBOM, source archive, `ffmpeg-build.json`, and a metadata-complete `runtime-manifest.json`. `scripts/assemble-bundled-runtime.ps1` copies only these prebuilt, reviewed inputs into a new payload directory and refuses to overwrite an existing one; it does not compile or download third-party code. Run `npm run generate:bundled-manifest -- <runtime-directory>` after every final payload change. It hashes every shipped artifact and refreshes the FFmpeg source-archive record; it does not invent release metadata. Then run `npm run audit:bundled-runtime -- <runtime-directory>` and `npm run verify:bundled-runtime -- <runtime-directory>` on Windows before publishing the payload for packaging. The executable verification imports the required packages, loads PyAV, checks both FFmpeg tools, and rejects GPL/nonfree configuration or libx264/libx265. `package:bundled-win` makes a missing runtime a hard error.
