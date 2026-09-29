# Issue 83 yt-dlp wheel alternative (Phase 1A)

Status: **promising local candidate, not an approved release input** (September 28, 2026). This is an alternative to bundling the official PyInstaller `yt-dlp.exe`; it does not change the running app, installer, or approved Phase 0 scope.

## Why investigate it

The current executable is self-contained but carries another Python runtime and numerous embedded native/third-party packages. [yt-dlp's licensing documentation](https://github.com/yt-dlp/yt-dlp/blob/2026.08.19/README.md#licensing) says its PyInstaller executables contain GPLv3+ code, whereas its PyPI wheel contains yt-dlp's Unlicense code. Reusing the already-planned private Python runtime could substantially simplify the source/notice map. This is an engineering packaging comparison, not a reason to avoid GPL obligations elsewhere (notably PyAV/FFmpeg).

## Exact local candidate evidence

| Input | SHA-256 | Source match and contents |
| --- | --- | --- |
| [yt_dlp-2026.8.19-py3-none-any.whl](https://pypi.org/project/yt-dlp/2026.8.19/) | `1d57897e94c6665a0a6f9bc54b34e584284e32c034ffab3a7df25d8f7b24eedf` | No `.dll`, `.pyd`, or `.exe`; contains an Unlicense file. All 1,049 `yt_dlp/` files matched the PyPI source archive byte-for-byte. |
| [yt_dlp-2026.8.19.tar.gz](https://pypi.org/project/yt-dlp/2026.8.19/) | `9e213e48cea35c66b378e4447903f118f6392a5fa380a2b6d7070ec86f4e0af1` | Published source archive for the same version; all 1,049 packaged Python/data files were compared. This is a different archive from the GitHub release's `yt-dlp.tar.gz`. |
| [yt_dlp_ejs-0.8.0-py3-none-any.whl](https://pypi.org/project/yt-dlp-ejs/0.8.0/) | `79300e5fca7f937a1eeede11f0456862c1b41107ce1d726871e0207424f4bdb4` | No native executable/DLL; includes two built/minified JavaScript files. Its metadata declares `Unlicense AND MIT AND ISC`. Its `LICENSE` file contains only Unlicense, while the generated `lib.min.js` banner includes the astring MIT and meriyah ISC notice texts. |
| [yt_dlp_ejs-0.8.0.tar.gz](https://pypi.org/project/yt-dlp-ejs/0.8.0/) | `d5fa1639f63b5c4af8d932495f60689d5370f1a095782c944f7f62a303eb104e` | Contains TypeScript source, `hatch_build.py`, `package-lock.json`, `deno.lock`, and other JS lockfiles. The four wheel Python files matched this source archive. Its two generated `.min.js` wheel files were subsequently reproduced byte-for-byte as described below. |

The pinned [yt-dlp 2026.08.19 package recipe](https://github.com/yt-dlp/yt-dlp/blob/2026.08.19/pyproject.toml) specifies `yt-dlp-ejs==0.8.0` for its `default` extra. The EJS source archive's `package-lock.json` pins the two third-party packages included in its built JS:

| JS source package | Source archive SHA-256 | Lockfile integrity | License |
| --- | --- | --- | --- |
| [astring 1.9.0](https://registry.npmjs.org/astring/-/astring-1.9.0.tgz) | `422cca9707aca293e85eb54fdbbc5a0a167ad415236a325ff342e720e67afb49` | SHA-512 SRI matched downloaded archive | MIT; archive contains `package/LICENSE` |
| [meriyah 6.1.4](https://registry.npmjs.org/meriyah/-/meriyah-6.1.4.tgz) | `c0f105d9fb01bb48c76ea6ee382e6099277b95e3f351fb99b67ddfb79d6088b8` | SHA-512 SRI matched downloaded archive | ISC; archive contains `package/LICENSE.md` |

The two wheels were installed **offline** with `--no-deps` into the ignored isolated Python 3.13.15 scratch runtime. `python -m yt_dlp --version` reported `2026.08.19`; both EJS solver scripts were visible as package resources. No system Python, project `.venv`, production runtime, installer, or user media was changed. These checks did not exercise a YouTube download or solve a live signature challenge.

### EJS build reproduction

The EJS source archive was extracted to ignored scratch. Its `hatch_build.py` specifies `npm ci` followed by `npm run bundle` when npm is the available builder. With local Node 24.12.0/npm 11.8.0, `npm ci --ignore-scripts --no-audit --no-fund` installed 189 lockfile-selected build packages, then `npm run bundle --offline` generated both shipped files. The source archive's `package-lock.json` SHA-256 is `dd1660d8db3804297a11e1769015e7a2b1390697cdf81c2a6905bd1dae292837`; `rollup.config.js` SHA-256 is `6add4d9bf3291a7fc5720103857faf4484a32b467fd1116a3d2ae6a6d14cf026`.

| Published wheel file | Rebuilt-file SHA-256 | Comparison |
| --- | --- | --- |
| `yt_dlp_ejs/yt/solver/core.min.js` | `18da6ce0758b416e7ae645084f4f8801f9f9d59d6c477c05eaa0ff94ebd8cc00` | 6,945 bytes; byte-identical |
| `yt_dlp_ejs/yt/solver/lib.min.js` | `c55987fe697e5b9ee18830163f7af85327e9bb5c3e674b969d38c8d205eaa577` | 151,561 bytes; byte-identical |

The `lib.min.js` banner names both astring 1.9.0 (MIT) and meriyah 6.1.4 (ISC) and embeds their notice texts. This closes the specific generated-file comparison, **not** the complete yt-dlp wheel/default-dependency, Deno, or release notice audits. The lockfile-selected build tools and the exact source archives still need to be represented appropriately in build documentation; generated notices must be carried into the Phase 2 release notice set.

## Pinned optional dependency expansion

The same yt-dlp source `pyproject.toml` also defines a `pin` extra for its default dependency family. A Windows x64 CPython 3.13 resolution of `yt-dlp[pin]==2026.8.19` downloaded the following 11 wheels into ignored scratch. Every cached file's SHA-256 matched its exact PyPI per-release JSON metadata. Native counts are `.dll`/`.pyd`/`.exe` entries inside each wheel; license labels are wheel metadata, not a completed license-text audit.

| Exact wheel filename | SHA-256 | Native files | Declared license |
| --- | --- | ---: | --- |
| `brotli-1.2.0-cp313-cp313-win_amd64.whl` | `b63daa43d82f0cdabf98dee215b375b4058cce72871fd07934f179885aad16e8` | 1 | MIT |
| `certifi-2026.7.22-py3-none-any.whl` | `62f22742b58a1a33014a2b6b706588a8d7e2a88ae7bd1a6ebe8c992928483775` | 0 | MPL-2.0 |
| `charset_normalizer-3.5.0-cp313-cp313-win_amd64.whl` | `72982d9958a42f8132bf2d6b90214ed66477295ef1188731f98ae3511c6eeb5a` | 2 | MIT |
| `idna-3.18-py3-none-any.whl` | `7f952cbe720b688055e3f87de14f5c3e5fdaa8bc3928985c4077ca689de849a2` | 0 | BSD-3-Clause |
| `mutagen-1.48.1-py3-none-any.whl` | `4f077fe87d3fc7fba259aa63d8c026b18382ca6a42ef37c61e16f1b1b5b82fe7` | 0 | GPL-2.0-or-later |
| `pycryptodomex-3.23.0-cp37-abi3-win_amd64.whl` | `52e5ca58c3a0b0bd5e100a9fbc8015059b05cffc6c66ce9d98b4b45e023443b9` | 42 | BSD/Public Domain in metadata |
| `requests-2.34.2-py3-none-any.whl` | `2a0d60c172f83ac6ab31e4554906c0f3b3588d37b5cb939b1c061f4907e278e0` | 0 | Apache-2.0 |
| `urllib3-2.7.0-py3-none-any.whl` | `9fb4c81ebbb1ce9531cce37674bbc6f1360472bc18ca9a553ede278ef7276897` | 0 | MIT |
| `websockets-17.0.1-cp313-cp313-win_amd64.whl` | `409d93efcaa14f7a99592c5baaef5ec6ca94fba0f5aec1a86f693977c69c9c1c` | 1 | BSD-3-Clause |
| `yt_dlp-2026.8.19-py3-none-any.whl` | `1d57897e94c6665a0a6f9bc54b34e584284e32c034ffab3a7df25d8f7b24eedf` | 0 | Unlicense |
| `yt_dlp_ejs-0.8.0-py3-none-any.whl` | `79300e5fca7f937a1eeede11f0456862c1b41107ce1d726871e0207424f4bdb4` | 0 | Unlicense AND MIT AND ISC |

All 11 installed **offline** to a new isolated Python 3.13.15 scratch target. Brotli, certifi, charset-normalizer, Cryptodome AES, idna, mutagen, requests, urllib3, websockets, yt-dlp, and yt-dlp-ejs imported; the CLI version path reported `2026.08.19`. This is dependency/import evidence, not a network or YouTube behavior test. The `pin` extra requests `idna==3.18`, while the current separate 26-wheel processing candidate has `idna==3.19`; a single reviewed combined lock must resolve that mismatch. `mutagen` is GPL-2.0-or-later, so this wheel route is not an MIT-only processing payload. Nine packages in this 11-wheel set are new to the current 26-wheel candidate list (certifi and idna overlap, with the version mismatch noted).

## What remains before selection

1. Decide the exact optional yt-dlp dependencies needed to preserve the current executable's behavior, then audit the eleven pinned wheel candidates above and their matching sources. The `curl-cffi` optional extra bundled in the current standalone executable is **not** in this set; site/browser-cookie behavior needs comparison. Reconcile idna 3.18 versus 3.19 in the combined lock. The separately bundled Deno remains required for the supported YouTube path. Do not silently use network-fetched EJS scripts in place of the local package.
2. Carry the reproduced EJS build recipe, lockfile, source archives, and embedded MIT/ISC notice texts into the matching source/notice companion; the EJS wheel's `LICENSE` file alone is insufficient for those components. The generated files now match exactly, but the release notice/source contract has not yet been implemented.
3. The app currently expects a `yt-dlp.exe` path and launches it as a subprocess. A wheel-based candidate needs a narrow private-Python `-m yt_dlp` invocation/adapter and shared readiness checks in Phase 4. The installed app must still offer an executable override/repair path where appropriate. This requires regression and offline/online functional tests before replacing the executable candidate.

For the other Phase 1A input, [Deno v2.9.6](https://github.com/denoland/deno/releases/tag/v2.9.6)'s tagged source archive was downloaded to ignored scratch and hashed at `d27f0ec13979c5dc76c7a0f20d5a389041746c005025102c1e220fa034674bbb` (32,718,531 bytes). Its `Cargo.lock` SHA-256 is `6c6af74640994cc41fcc7f46bb5204a50da679adc2dee96cb05aa97867baf7e1`; it records 1,046 crates.io sources with per-crate checksums and 82 workspace packages. The tagged CI recipe uses Rust 1.95.0, a locked release build, code signing, and ZIP publication. The Deno workspace selects `v8` crate 150.4.0 with `simdutf`; [rusty_v8's v150.4.0 build recipe](https://github.com/denoland/rusty_v8/blob/v150.4.0/build.rs) therefore points to [the Windows x64 `rusty_v8_simdutf_release` static library](https://github.com/denoland/rusty_v8/releases/download/v150.4.0/rusty_v8_simdutf_release_x86_64-pc-windows-msvc.lib.gz), 39,225,458 bytes. Its locally verified SHA-256 matched the official release digest `f231f82cbacb9aefe6d9af57e6df2e8959a40e001f79306485133e3c075b98f0`. The rusty_v8 v150.4.0 tag tree is Git SHA `5c15a6995c9bb4bacd3e341b59fff32c909c80bf` and pins its V8 submodule to `ac1e23989121713ca642f6650b34deff7b686896`. These are source/build anchors, **not** yet a complete map of the exact compiled crate subset, V8 submodules, notices, or host requirements beyond Deno's documented Windows 10/Server 2016 version 1709 floor.
