# Issue 83: narrow FFmpeg local build probe

Status: **functional Phase 1A candidate, not an approved release input** (September 28, 2026). The current installer remains Python-only. This probe does not change the application's dependency policy or establish legal clearance.

The initial FFmpeg/x264-only cross-build could encode H.264/AAC, but was insufficient for the application: `backend/censor/engine.py` uses `-c:a libmp3lame -q:a 4` for audio-only censorship. The revised build statically links LAME 3.100. Its only enabled external libraries are `libx264` and `libmp3lame`; `--disable-autodetect` prevents incidental optional-library pickup. Built-in FFmpeg codecs, filters, and Windows capture interfaces remain enabled. `-buildconf` contains `--enable-gpl --enable-version3` and no `--enable-nonfree`; `-L` reports GPL version 3 or later.

## Exact inputs and local outputs

| Input | Source | SHA-256 |
| --- | --- | --- |
| `ffmpeg-8.1.2.tar.xz` | [FFmpeg release archive](https://ffmpeg.org/releases/ffmpeg-8.1.2.tar.xz) | `464beb5e7bf0c311e68b45ae2f04e9cc2af88851abb4082231742a74d97b524c` |
| `x264-b35605ace3ddf7c1a5d67a2eb553f034aef41d55.tar.bz2` | [VideoLAN commit archive](https://code.videolan.org/videolan/x264/-/archive/b35605ace3ddf7c1a5d67a2eb553f034aef41d55/x264-b35605ace3ddf7c1a5d67a2eb553f034aef41d55.tar.bz2), also pinned by [PyAV's recipe](https://github.com/PyAV-Org/pyav-ffmpeg/blob/8.1.2-1/scripts/pkg.py) | `6eeb82934e69fd51e043bd8c5b0d152839638d1ce7aa4eea65a3fedcf83ff224` |
| `lame-3.100.tar.gz` | [LAME SourceForge release](https://sourceforge.net/projects/lame/files/lame/3.100/lame-3.100.tar.gz/download); the local hash matches its published SHA-256 and [PyAV's recipe](https://github.com/PyAV-Org/pyav-ffmpeg/blob/8.1.2-1/scripts/pkg.py) | `ddfe36cab873794038ae2c1210557ad34857a4b6bdc515785d1da9e175b1da1e` |

The build recipe is [Dockerfile](../scripts/issue83_ffmpeg/Dockerfile), [build.sh](../scripts/issue83_ffmpeg/build.sh), and [APT inventory helper](../scripts/issue83_ffmpeg/record-apt-inputs.sh); [local instructions](../scripts/issue83_ffmpeg/README.md) describe the ignored scratch input/output directories. The Debian Bookworm slim base image is digest-pinned at `sha256:3783cc01769c7b2b1b83a5c5ad96c815348e28ed7da68e2e3687004faa906251`. Debian binary/source indexes are pinned to the `20260928T000000Z` snapshot, with APT signature and package-hash verification. The complete 149-package version list hashes to `8cfef7bd587924f96537353a5a69e6bb7dc209c7c4d446a0856c016d58ba2545`. The corresponding [package/archive/source mapping](ISSUE83_FFMPEG_APT_INPUTS.txt) hashes to `cfb9aca689fe62fe970bb835a14b0ad85a53cf0d40704ea48ca2cd80661efb22`; the builder now checks both before compilation. Relevant observed versions were MinGW GCC 12.2.0 (`12.2.0-14+deb12u1+25.2+b1` runtime), binutils 2.40-2+10.4, NASM 2.16.01-1, and make 4.3-4.1. The builder verifies all three FFmpeg/x264/LAME source hashes before compilation and retains FFmpeg `config.h`/`config.mak`, source/binary hashes, and toolchain metadata. No source changes or patches were applied by this recipe. The source-package archives are located and hashed by the signed snapshot indexes, but are not yet retained in a source companion.

The successful local outputs are ignored scratch, not tracked or installed. The package-version guard was added after `attempt4`; a full guarded run in `attempt5` produced both executables but its PowerShell log wrapper misreported compiler warnings as an error. A later snapshot-pinned build, `attempt6`, exited cleanly and passed the H.264/AAC, muted-MP3, conversion, and preserve-source probes. `attempt7` added the full package/archive hash guard and also exited cleanly. `attempt8` used a fixed build prefix, exited cleanly, and passed the repeatable smoke check. Its hashes below identify the current functional candidate, not an approved installer input.

| Binary | Size | SHA-256 |
| --- | ---: | --- |
| `ffmpeg.exe` | 26,061,824 bytes | `30e8c60c3ff0d3393098962507352c61195f027e48946f99f034df3720276bff` |
| `ffprobe.exe` | 25,856,000 bytes | `4d051f3ef78deff0ba00b4116a777b32bdfe80221c47216c23daf4c6ad3fb253` |

The guarded `attempt5` binaries are also 26,061,824 and 25,856,000 bytes. Their SHA-256 values are `469c2e35cfb9a44269f1371fc166ec3ce14f0986a3ec6f41be4c6980ed525e70` (`ffmpeg.exe`) and `29ea9c45c8c53841c874da0e1339e40b068aa3dfa45592d562bedc258fa3155f` (`ffprobe.exe`). The earlier variable temporary build prefix appeared in `-buildconf`; the current recipe fixes it, but byte-identical rebuilds have not yet been demonstrated.

| Fixed-prefix `attempt8` output | Size | SHA-256 |
| --- | ---: | --- |
| `ffmpeg.exe` | 26,061,824 bytes | `e7b3c6815ce897c600bebb0df98d13798c2020fc235b75d84195808e25ec2c9f` |
| `ffprobe.exe` | 25,856,000 bytes | `c7c65753fdeed949b93aa759235b2833c95f00f1abc529a109b609f9ceff27ea` |

The `attempt8` checksum file also matches the three upstream source archives and both guarded Debian input inventories. `ffmpeg -version` reports version 8.1.2, the fixed `/tmp/issue83-ffmpeg-build/install` prefix, `--enable-gpl --enable-version3 --enable-libx264 --enable-libmp3lame --disable-autodetect`, and no `--enable-nonfree`. `-L` reports GPL version 3 or later. These are observed local results, not a claim of byte-identical reproducibility or complete distribution compliance.

The source archives contain `ffmpeg-8.1.2/LICENSE.md` and `COPYING.GPLv3`, x264 `COPYING`, and LAME `COPYING` and `LICENSE`. LAME's `LICENSE` identifies the library under the LGPL, and its library source headers say GNU Library GPL version 2 or later. Debian's signed source index identifies MinGW-w64 10.0.0-3 (source tar SHA-256 `ba6b430aed72c63a3768531f6a3ffc2b0fde2c57a3b251450dcf489a894f0894`), gcc-mingw-w64 25.2 (source tar SHA-256 `a7e141adfc524cf2cff65a0d5da66ab24f1a73b69d44f562852ca0a3674044d9`), and GCC 12.2.0-14+deb12u1 (orig tar SHA-256 `b8298be16aeeb96a889c6afed0a8e2241b47452e89cc81fe65ea849d5c740fcb`, Debian patch tar SHA-256 `59f7f7763a0c355e3f27ff9e7ac80d06382b29939361a87e7b139226bfe7402e`). These are source/notice anchors, not yet a generated release notice set or a complete statutory analysis. The statically linked binary is the GPLv3+ FFmpeg program; do not label it MIT-only.

## Functional checks performed on Windows

- `ffmpeg -version`, `-buildconf`, `-L`, `-encoders`, and `ffprobe -version` ran. The encoder list includes `libx264`, `aac`, and `libmp3lame`.
- MinGW `objdump -p` on both `attempt8` EXEs listed only Windows system DLL imports (`bcrypt`, `GDI32`, `KERNEL32`, `msvcrt`, `ole32`, `OLEAUT32`, `SHELL32`, `SHLWAPI`, `USER32`, `AVICAP32`, and `WS2_32`). No third-party or GPU-runtime DLL import appeared. This is an import-table check, not a complete runtime-dependency proof.
- Synthetic H.264/AAC MP4 creation, MPEG-4/AAC to H.264/AAC conversion, and audio-only WAV to muted MP3 using the app's `libmp3lame -q:a 4` invocation all succeeded; FFprobe reported the expected streams.
- App-style `-af volume=0:enable='between(t,0.25,0.75)' -c:v copy -c:a aac` produced a readable MP4. The source and muted output's copied video stream each hashed to `cbe854a8e0dcda0a91b662beb4225cbb37b6897b67fcd8f003e5783a33796c48` with FFmpeg's SHA-256 hash muxer.
- The repeatable [synthetic smoke script](../scripts/issue83_ffmpeg/smoke.ps1) passed against the archive-hash-guarded `attempt7` and fixed-prefix `attempt8` outputs, checking forced H.264/AAC, the copied video stream, MP3 output, and an unchanged source-file SHA-256.
- The app's `available_encoders`/`select_working_video_encoder` path selected `libx264` on this host. The builder's Bash syntax check passed.

All media in these checks was generated locally in ignored scratch. No user media, installer, or release asset was changed. The old x264-only prototype in `narrow-ffmpeg-attempt3` must **not** be selected; it lacks MP3 output.

## Remaining Phase 1A gates

- Retain the source-package archives and any compiler-runtime notices needed for statically linked MinGW/GCC code in the Phase 2 companion. The snapshot and package hashes now locate the exact build inputs; Phase 7 checks a clean rebuild from retained materials. A byte-identical result is not yet claimed.
- Record a release-ready corresponding-source companion and complete notices for FFmpeg, x264, LAME, and any statically included toolchain runtime. Review license interaction and replacement/relinking obligations for the selected static linkage. Phase 2 generates and validates those materials against the reviewed input lock.
- Record supported Windows/CPU prerequisites and test on the supported host range. The import table alone cannot prove clean-host operation; the real installer qualification is Phase 7.
- Finish the other Phase 1A tools (CPython/pip, yt-dlp/EJS, Deno) and all Phase 1B wheel/native-library gates before allowing these binaries into Phase 3 assembly.
- Include MP3, alongside H.264/AAC, in Phase 8's review of the actual shipped codec set; this local build does not resolve patent coverage.
