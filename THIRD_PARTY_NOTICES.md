# Third-Party Notices

Expletive Deleted includes, uses, or can retrieve third-party software and
data. Those materials remain subject to their own copyright notices and
license terms. The Expletive Deleted MIT License does not replace those terms.

This inventory was prepared from the `main` branch of
[`Nerotas/expletive-deleted`](https://github.com/Nerotas/expletive-deleted)
at commit
[`92f4687d81f973d0b1b77d7824853419a70c435e`](https://github.com/Nerotas/expletive-deleted/commit/92f4687d81f973d0b1b77d7824853419a70c435e)
(2026-09-02). Versions below are the versions pinned by `package-lock.json`,
`requirements.txt`, or the runtime setup code at that commit.

This file is an informational inventory, not legal advice and not a warranty
that every possible transitive or platform-supplied component is listed.

## 1. Included in the Windows application

The release configuration includes the compiled Electron application, the
compiled renderer and its fonts, the first-party Python source, resources, and
`requirements.txt`. The package audit rejects processing `ffmpeg.exe` and
`ffprobe.exe` files, Whisper model payloads, Python wheels and Python extension
modules. Python itself is not included.

### Electron runtime

| Component | Version | License | Project |
| --- | ---: | --- | --- |
| Electron | 44.0.0 | MIT | [electron/electron](https://github.com/electron/electron/tree/v44.0.0) |

Electron includes Chromium, Node.js, V8, and other third-party components.
Electron distributions provide the detailed Chromium notices in
`LICENSES.chromium.html`; packaged copies of that file and Electron's license
file should be retained with the application. Electron's framework-owned
`ffmpeg.dll` is Chromium codec support. It is not the separately retrieved
FFmpeg/FFprobe processing runtime described in section 2.

Electron notice:

> Copyright (c) Electron contributors
> Copyright (c) 2013-2020 GitHub Inc.

Electron is licensed under the MIT License text in Appendix A. See the
[Electron 44.0.0 license](https://github.com/electron/electron/blob/v44.0.0/LICENSE)
and [Chromium notices shipped by Electron](https://github.com/electron/electron/blob/v44.0.0/LICENSES.chromium.html).

### Compiled renderer libraries

The following packages are direct or transitive production packages in the
locked frontend dependency graph and are compiled into, or used by, the
renderer bundle.

| Component | Version | License | Copyright/notice source |
| --- | ---: | --- | --- |
| React; React DOM | 19.2.8 | MIT | Copyright (c) Meta Platforms, Inc. and affiliates; [React](https://www.npmjs.com/package/react/v/19.2.8) |
| Scheduler | 0.27.0 | MIT | Copyright (c) Meta Platforms, Inc. and affiliates; [Scheduler](https://www.npmjs.com/package/scheduler/v/0.27.0) |
| TanStack Query Core; TanStack React Query | 5.102.8 | MIT | Copyright (c) 2021-present Tanner Linsley; [TanStack Query](https://github.com/TanStack/query/tree/v5.102.8) |
| React Hook Form | 7.86.0 | MIT | Copyright (c) 2019-present Beier(Bill) Luo; [React Hook Form](https://www.npmjs.com/package/react-hook-form/v/7.86.0) |
| React Router; React Router DOM | 7.18.3 | MIT | Copyright (c) React Training LLC 2015-2019; Remix Software Inc. 2020-2021; Shopify Inc. 2022-2023; [React Router](https://www.npmjs.com/package/react-router/v/7.18.3) |
| cookie | 1.1.1 | MIT | Copyright (c) 2012-2014 Roman Shtylman; Copyright (c) 2015 Douglas Christopher Wilson; [cookie](https://www.npmjs.com/package/cookie/v/1.1.1) |
| set-cookie-parser | 2.7.2 | MIT | Copyright (c) 2015 Nathan Friedly; [set-cookie-parser](https://www.npmjs.com/package/set-cookie-parser/v/2.7.2) |
| Lucide React | 1.34.0 | ISC; some icons derived from Feather are MIT | Copyright (c) 2026 Lucide Icons and Contributors; derived Feather icons Copyright (c) 2013-present Cole Bemis; [Lucide React](https://www.npmjs.com/package/lucide-react/v/1.34.0) |

The MIT terms for the MIT-licensed entries are in Appendix A. Lucide's ISC
notice and its Feather notice are in Appendix B.

### Bundled fonts

Only the font weights imported by `frontend/src/index.css` are compiled into
the renderer. The locked Fontsource packages and upstream font notices are:

| Font | Fontsource version | License | Copyright notice |
| --- | ---: | --- | --- |
| Manrope | 5.3.0 | SIL Open Font License 1.1 | Copyright 2019 The Manrope Project Authors ([upstream](https://github.com/sharanda/manrope)) |
| Source Serif 4 | 5.3.0 | SIL Open Font License 1.1 | Google Inc. ([Fontsource package](https://www.npmjs.com/package/@fontsource/source-serif-4/v/5.3.0)) |
| IBM Plex Mono | 5.3.0 | SIL Open Font License 1.1 | Copyright 2017 IBM Corp. All rights reserved. ([upstream](https://github.com/IBM/plex)) |

The SIL Open Font License 1.1 is reproduced in Appendix C.

## 2. Not bundled; installed or retrieved separately after user approval

The application can prepare an inspectable setup plan and, after the user
approves it, install or download the following items into the user's Python
environment or local application-data directories. A user can instead select
a compatible installation already present on the system.

### Python and Python packages

Python 3.9 or later is supplied separately by the user and is not distributed
by the Expletive Deleted installer. Python versions are subject to the license
terms accompanying the selected Python distribution.

The current `requirements.txt` pins these direct packages:

| Package | Version | Declared license | Authoritative metadata/source |
| --- | ---: | --- | --- |
| faster-whisper | 1.2.1 | MIT | [PyPI metadata](https://pypi.org/project/faster-whisper/1.2.1/), [source](https://github.com/SYSTRAN/faster-whisper) |
| better-profanity | 0.7.0 | MIT | [PyPI metadata](https://pypi.org/project/better-profanity/0.7.0/), [source](https://github.com/snguyenthanh/better_profanity) |
| NumPy | 2.5.2 | `BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0` | [PyPI metadata](https://pypi.org/project/numpy/2.5.2/), including bundled-component notices in the distribution |
| CTranslate2 | 4.8.1 | MIT | [PyPI metadata](https://pypi.org/project/ctranslate2/4.8.1/), [source](https://github.com/OpenNMT/CTranslate2) |
| PyAV source | 18.1.0 | BSD-3-Clause | [PyPI metadata](https://pypi.org/project/av/18.1.0/), [source](https://github.com/PyAV-Org/PyAV) |
| huggingface-hub | 1.28.0 | Apache-2.0 | [PyPI metadata](https://pypi.org/project/huggingface-hub/1.28.0/), [source](https://github.com/huggingface/huggingface_hub) |

Package installers may also resolve transitive dependencies and
platform-specific binary components. Their exact set can vary with the Python
version, platform, package index, and selected wheel. Their own distribution
metadata and bundled license files are controlling for those separately
installed copies.

Important Windows-wheel qualification: the official
`av-18.1.0-cp311-abi3-win_amd64.whl` available from PyPI was inspected for
this inventory. Although its package metadata identifies the PyAV source as
BSD-3-Clause, the wheel bundles FFmpeg shared libraries together with
`libx264` and `libx265`. Those libraries make the bundled FFmpeg build subject
to GPL terms; this is also documented in
[PyAV issue #2270](https://github.com/PyAV-Org/PyAV/issues/2270). Anyone who
redistributes that binary wheel should evaluate and satisfy the GPL and all
included-library notice/source obligations, rather than relying only on the
BSD-3-Clause label in PyAV's package metadata.

The setup code also supports `openai-whisper==20250625` (MIT) as an optional
alternative Whisper library, although it is not in the default
`requirements.txt`. See [PyPI metadata](https://pypi.org/project/openai-whisper/20250625/)
and the [OpenAI Whisper source license](https://github.com/openai/whisper/blob/main/LICENSE).

### FFmpeg and FFprobe processing runtime

FFmpeg and FFprobe executables are **not bundled** with the Windows installer.
If the user chooses managed setup, the application first installs
`static-ffmpeg==3.0` (the downloader is MIT-licensed) from PyPI, then asks that
package to retrieve platform executables and copies the resulting files into
the user's local application runtime directory. See the
[`static-ffmpeg` PyPI metadata](https://pypi.org/project/static-ffmpeg/3.0/)
and [upstream source](https://github.com/zackees/static_ffmpeg).

For Windows, `static-ffmpeg==3.0` currently resolves its fixed legacy URL to
the Gyan FFmpeg 8.0.1 essentials build. Inspection of the retrieved executable
shows `--enable-gpl`, `--enable-version3`, `--enable-libx264`, and
`--enable-libx265`; Gyan identifies its static Windows builds as GPLv3. Thus,
the managed Windows binary is not merely an unspecified LGPL build. See
[Gyan's build and licensing information](https://www.gyan.dev/ffmpeg/builds/).

FFmpeg does not have one license that applies identically to every binary.
The FFmpeg project is primarily LGPL version 2.1 or later, but enabling
optional GPL components makes a build GPL version 2 or later, and enabling
certain nonfree components can make the resulting binary non-redistributable.
The actual license and configuration therefore depend on the build the user
already has or that the retrieval tool obtains; the current managed Windows
path described above is GPLv3. Users and redistributors should inspect that
build's accompanying notices and `ffmpeg -version` configuration. See
[FFmpeg Legal](https://ffmpeg.org/legal.html) and the
[FFmpeg license documentation](https://ffmpeg.org/doxygen/trunk/md_LICENSE.html).

`ffprobe` is part of the same FFmpeg project and follows the applicable terms
of the selected FFmpeg build.

### Whisper large-v3 model

The supported default model is
[`Systran/faster-whisper-large-v3`](https://huggingface.co/Systran/faster-whisper-large-v3),
pinned by the setup code to revision
`edaa852ec7e145841d8ffdb056a99866b5f0a478`. It is downloaded separately into
the user's cache and is not included in the installer. The pinned model card
declares the converted model MIT-licensed and identifies it as a CTranslate2
conversion of `openai/whisper-large-v3`. See the
[pinned model card](https://huggingface.co/Systran/faster-whisper-large-v3/blob/edaa852ec7e145841d8ffdb056a99866b5f0a478/README.md)
and [original model card](https://huggingface.co/openai/whisper-large-v3).

Other Whisper model/library choices supported by the source may retrieve
different model artifacts; their accompanying model cards and license files
apply to those user-selected downloads.

## 3. Development and build tooling

These direct locked dependencies are used to develop, test, or package the
application. They are not renderer runtime libraries. Electron is declared as
a development dependency for build purposes but its runtime is included in
the packaged app and is therefore covered in section 1.

| Package | Locked version | Declared license |
| --- | ---: | --- |
| @eslint/js | 10.0.1 | MIT |
| @testing-library/jest-dom | 6.9.1 | MIT |
| @testing-library/react | 16.3.3 | MIT |
| @testing-library/user-event | 14.6.6 | MIT |
| @types/node | 24.13.3 | MIT |
| @types/react | 19.2.18 | MIT |
| @types/react-dom | 19.2.5 | MIT |
| @vitejs/plugin-react | 5.2.0 | MIT |
| electron-builder | 26.15.3 | MIT |
| electron-vite | 5.0.0 | MIT |
| esbuild | 0.25.12 | MIT |
| ESLint | 10.9.1 | MIT |
| eslint-plugin-react-hooks | 7.1.1 | MIT |
| eslint-plugin-react-refresh | 0.5.5 | MIT |
| globals | 17.11.0 | MIT |
| jsdom | 29.1.1 | MIT |
| Playwright | 1.62.1 | Apache-2.0 |
| TypeScript | 6.0.3 | Apache-2.0 |
| typescript-eslint | 8.68.0 | MIT |
| Vite | 7.3.6 | MIT |
| Vitest | 4.1.11 | MIT |

The lockfile contains additional transitive build dependencies. Their package
metadata and license files remain applicable. GitHub Actions used by the
release workflow are build-service inputs and are not included in the
application installer.

## Appendix A — MIT License

The following text applies to each MIT-licensed component identified above,
with the copyright notice listed for that component or supplied in its own
distribution:

> Permission is hereby granted, free of charge, to any person obtaining a copy
> of this software and associated documentation files (the "Software"), to deal
> in the Software without restriction, including without limitation the rights
> to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
> copies of the Software, and to permit persons to whom the Software is
> furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all
> copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
> IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
> FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
> AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
> LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
> OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
> SOFTWARE.

## Appendix B — Lucide and Feather notices

Lucide ISC License:

> Copyright (c) 2026 Lucide Icons and Contributors
>
> Permission to use, copy, modify, and/or distribute this software for any
> purpose with or without fee is hereby granted, provided that the above
> copyright notice and this permission notice appear in all copies.
>
> THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
> WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
> MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY
> SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
> WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION
> OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN
> CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

Lucide identifies some icons as derived from Feather. The list of affected
icons is maintained in the
[`lucide-react` 1.34.0 license file](https://unpkg.com/lucide-react@1.34.0/LICENSE).
Those icons carry this MIT notice:

> Copyright (c) 2013-present Cole Bemis

The MIT terms in Appendix A apply to those Feather-derived icons.

## Appendix C — SIL Open Font License 1.1

> SIL OPEN FONT LICENSE Version 1.1 - 26 February 2007
>
> PREAMBLE
>
> The goals of the Open Font License (OFL) are to stimulate worldwide
> development of collaborative font projects, to support the font creation
> efforts of academic and linguistic communities, and to provide a free and
> open framework in which fonts may be shared and improved in partnership with
> others.
>
> The OFL allows the licensed fonts to be used, studied, modified and
> redistributed freely as long as they are not sold by themselves. The fonts,
> including any derivative works, can be bundled, embedded, redistributed
> and/or sold with any software provided that any reserved names are not used
> by derivative works. The fonts and derivatives, however, cannot be released
> under any other type of license. The requirement for fonts to remain under
> this license does not apply to any document created using the fonts or their
> derivatives.
>
> DEFINITIONS
>
> "Font Software" refers to the set of files released by the Copyright
> Holder(s) under this license and clearly marked as such. This may include
> source files, build scripts and documentation.
>
> "Reserved Font Name" refers to any names specified as such after the
> copyright statement(s).
>
> "Original Version" refers to the collection of Font Software components as
> distributed by the Copyright Holder(s).
>
> "Modified Version" refers to any derivative made by adding to, deleting, or
> substituting -- in part or in whole -- any of the components of the Original
> Version, by changing formats or by porting the Font Software to a new
> environment.
>
> "Author" refers to any designer, engineer, programmer, technical writer or
> other person who contributed to the Font Software.
>
> PERMISSION & CONDITIONS
>
> Permission is hereby granted, free of charge, to any person obtaining a copy
> of the Font Software, to use, study, copy, merge, embed, modify, redistribute,
> and sell modified and unmodified copies of the Font Software, subject to the
> following conditions:
>
> 1) Neither the Font Software nor any of its individual components, in
> Original or Modified Versions, may be sold by itself.
>
> 2) Original or Modified Versions of the Font Software may be bundled,
> redistributed and/or sold with any software, provided that each copy
> contains the above copyright notice and this license. These can be included
> either as stand-alone text files, human-readable headers or in the
> appropriate machine-readable metadata fields within text or binary files as
> long as those fields can be easily viewed by the user.
>
> 3) No Modified Version of the Font Software may use the Reserved Font Name(s)
> unless explicit written permission is granted by the corresponding Copyright
> Holder. This restriction only applies to the primary font name as presented
> to the users.
>
> 4) The name(s) of the Copyright Holder(s) or the Author(s) of the Font
> Software shall not be used to promote, endorse or advertise any Modified
> Version, except to acknowledge the contribution(s) of the Copyright
> Holder(s) and the Author(s) or with their explicit written permission.
>
> 5) The Font Software, modified or unmodified, in part or in whole, must be
> distributed entirely under this license, and must not be distributed under
> any other license. The requirement for fonts to remain under this license
> does not apply to any document created using the Font Software.
>
> TERMINATION
>
> This license becomes null and void if any of the above conditions are not
> met.
>
> DISCLAIMER
>
> THE FONT SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
> OR IMPLIED, INCLUDING BUT NOT LIMITED TO ANY WARRANTIES OF MERCHANTABILITY,
> FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT OF COPYRIGHT, PATENT,
> TRADEMARK, OR OTHER RIGHT. IN NO EVENT SHALL THE COPYRIGHT HOLDER BE LIABLE
> FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, INCLUDING ANY GENERAL, SPECIAL,
> INDIRECT, INCIDENTAL, OR CONSEQUENTIAL DAMAGES, WHETHER IN AN ACTION OF
> CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF THE USE OR INABILITY TO USE
> THE FONT SOFTWARE OR FROM OTHER DEALINGS IN THE FONT SOFTWARE.
