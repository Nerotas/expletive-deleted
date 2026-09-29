# Issue 83 narrow FFmpeg build prototype

This is a local Phase 1A candidate, not an approved installer input. It cross-builds
Windows x64 FFmpeg/FFprobe 8.1.2, x264, and LAME 3.100 from exact upstream
source archives. LAME is required by the application's audio-only MP3 output;
the first x264-only prototype lacked that encoder. No GPU SDK/runtime or other
optional codec library is included. Built-in decoders, AAC encoding, and media
filters remain enabled; verify actual application workflows before selection.

Place the three source archives named in `build.sh` in an ignored input directory,
then run (PowerShell, from the repository root):

```powershell
$scratch = Join-Path (Resolve-Path .).Path 'tmp/issue83-artifacts'
$output = Join-Path $scratch 'narrow-ffmpeg'
New-Item -ItemType Directory -Path $output | Out-Null
docker build --pull=false -t issue83-ffmpeg-probe scripts/issue83_ffmpeg
docker run --rm --cpus 4 --memory 8g `
  --mount "type=bind,source=$scratch,target=/inputs,readonly" `
  --mount "type=bind,source=$output,target=/output" issue83-ffmpeg-probe
```

Use a new empty output directory for each attempt. The builder verifies source hashes before
compiling and retains the resulting binary hashes, configuration, toolchain versions,
and each installed package's signed Debian archive SHA-256/source-package mapping.
Use only ignored scratch directories for inputs/outputs. The Docker base image is
digest-pinned, and both `deb` and `deb-src` indexes come from the September 28, 2026
Debian snapshot. APT verifies Debian signatures and package hashes even though this
container uses the snapshot's HTTP endpoint (its HTTPS chain is not trusted in this
local Docker environment). The builder fails if its complete package/version list or
archive-hash inventory differs from the tested values. The exact 149-package input
record is [tracked here](../../docs/ISSUE83_FFMPEG_APT_INPUTS.txt); the matching source
archives still need to be retained for the Phase 2 companion. The output must pass `-version`, `-buildconf`, `-L`, a forced
CPU `libx264` encode/FFprobe check, `libmp3lame` audio encode, and the application's local processing
smoke tests. A source companion and full license review are still required.

Run the repeatable synthetic-media smoke check against a completed output directory:

```powershell
& scripts/issue83_ffmpeg/smoke.ps1 -BinaryDirectory $output -ScratchRoot $scratch
```

It uses a fresh scratch child, verifies H.264/AAC and MP3 output, checks the copied
video stream, and confirms its synthetic source file was not changed. It does not
replace a clean-host installer or end-to-end transcription test.
