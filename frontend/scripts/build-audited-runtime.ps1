[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$PythonRuntimeDirectory,
    [Parameter(Mandatory)][string]$FfmpegPrefix,
    [Parameter(Mandatory)][string]$FfmpegSourceDirectory,
    [Parameter(Mandatory)][string]$OutputDirectory
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$frontendRoot = Split-Path -Parent $PSScriptRoot
$repositoryRoot = Split-Path -Parent $frontendRoot
$workRoot = Join-Path $env:RUNNER_TEMP 'audited-runtime-build'
$pythonDirectory = [IO.Path]::GetFullPath($PythonRuntimeDirectory)
$pythonExecutable = Join-Path $pythonDirectory 'python.exe'
$ffmpegRoot = [IO.Path]::GetFullPath($FfmpegPrefix)
$ffmpegBin = Join-Path $ffmpegRoot 'bin'
$metadataRoot = Join-Path $workRoot 'metadata'
$ytdlpRoot = Join-Path $workRoot 'ytdlp'
$denoRoot = Join-Path $workRoot 'deno'
$pyavSource = Join-Path $workRoot 'PyAV'
$wheelDirectory = Join-Path $workRoot 'wheels'
$sitePackages = Join-Path $pythonDirectory 'Lib\site-packages'
$configure = @(
    '--disable-static',
    '--enable-shared',
    '--disable-doc',
    '--disable-debug',
    '--disable-gpl',
    '--disable-nonfree',
    '--disable-autodetect'
)

foreach ($path in @($pythonExecutable, (Join-Path $ffmpegBin 'ffmpeg.exe'), (Join-Path $ffmpegBin 'ffprobe.exe'))) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Required runtime build input is missing: $path" }
}
if (Test-Path -LiteralPath $workRoot) { Remove-Item -LiteralPath $workRoot -Recurse -Force }
New-Item -ItemType Directory -Path $metadataRoot, $ytdlpRoot, $denoRoot, $wheelDirectory | Out-Null

$runtimeRequirements = Join-Path $workRoot 'requirements-runtime.txt'
Get-Content (Join-Path $repositoryRoot 'requirements.txt') |
Where-Object { $_ -notmatch '^av==' } |
Set-Content -LiteralPath $runtimeRequirements -Encoding ascii

python -m pip install --disable-pip-version-check --upgrade Cython setuptools wheel
if ($LASTEXITCODE -ne 0) { throw 'Installing PyAV build dependencies failed.' }
git clone --quiet https://github.com/PyAV-Org/PyAV.git $pyavSource
if ($LASTEXITCODE -ne 0) { throw 'Cloning PyAV failed.' }
git -C $pyavSource checkout --quiet 7e3d950a8b72062502c1a60d672f8ca565313af5
if ($LASTEXITCODE -ne 0) { throw 'Checking out audited PyAV source failed.' }
Push-Location $pyavSource
try {
    python setup.py bdist_wheel "--ffmpeg-dir=$ffmpegRoot" --dist-dir $wheelDirectory
    if ($LASTEXITCODE -ne 0) { throw 'Building PyAV against the LGPL FFmpeg libraries failed.' }
}
finally {
    Pop-Location
}
$pyavWheel = Get-ChildItem -LiteralPath $wheelDirectory -Filter 'av-18.1.0-*.whl' | Select-Object -First 1
if (-not $pyavWheel) { throw 'The audited PyAV build did not produce an av 18.1.0 wheel.' }
python -m pip install --disable-pip-version-check --no-compile --upgrade --target $sitePackages $pyavWheel.FullName -r $runtimeRequirements
if ($LASTEXITCODE -ne 0) { throw 'Installing the private Python dependencies failed.' }

$originalPath = $env:PATH
$env:PATH = "$ffmpegBin;$originalPath"
try {
    & $pythonExecutable -I -c "import av, ctranslate2, faster_whisper, numpy, better_profanity, huggingface_hub; assert av.__version__ == '18.1.0'; assert av.library_versions; print('Source-built PyAV and private Python dependencies verified')"
    if ($LASTEXITCODE -ne 0) { throw 'The assembled private Python dependencies failed verification.' }
    & $pythonExecutable -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'The assembled private Python dependency graph is inconsistent.' }
}
finally {
    $env:PATH = $originalPath
}

Get-ChildItem -LiteralPath $pythonDirectory -Filter '*.whl' -File -Recurse | Remove-Item -Force
python (Join-Path $repositoryRoot 'scripts\download_ytdlp.py') --root $workRoot
if ($LASTEXITCODE -ne 0) { throw 'Downloading yt-dlp failed.' }
python (Join-Path $repositoryRoot 'scripts\download_deno_runtime.py') --root $workRoot
if ($LASTEXITCODE -ne 0) { throw 'Downloading Deno failed.' }
Copy-Item -LiteralPath (Join-Path $workRoot 'dependencies\yt-dlp\yt-dlp.exe') -Destination (Join-Path $ytdlpRoot 'yt-dlp.exe')
Copy-Item -LiteralPath (Join-Path $workRoot 'dependencies\deno\deno.exe') -Destination (Join-Path $denoRoot 'deno.exe')

$licensesRoot = Join-Path $metadataRoot 'LICENSES'
New-Item -ItemType Directory -Path $licensesRoot | Out-Null
Copy-Item -LiteralPath (Join-Path $pythonDirectory 'LICENSE.txt') -Destination (Join-Path $licensesRoot 'python.txt')
Copy-Item -LiteralPath (Join-Path $FfmpegSourceDirectory 'COPYING.LGPLv2.1') -Destination (Join-Path $licensesRoot 'ffmpeg.txt')
Copy-Item -LiteralPath (Join-Path $pyavSource 'LICENSE') -Destination (Join-Path $licensesRoot 'pyav.txt')

$licensePackages = @{
    'faster-whisper'   = 'faster-whisper.txt'
    'numpy'            = 'numpy.txt'
    'better-profanity' = 'better-profanity.txt'
    'huggingface-hub'  = 'huggingface-hub.txt'
}
foreach ($distribution in $licensePackages.Keys) {
    $licensePath = & $pythonExecutable -c "import importlib.metadata as m,sys; d=m.distribution(sys.argv[1]); print(next(str(d.locate_file(f)) for f in d.files if '/license' in str(f).replace(chr(92),'/').lower() or str(f).replace(chr(92),'/').lower().endswith('/copying')))" $distribution
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $licensePath)) { throw "License file was not found for $distribution." }
    Copy-Item -LiteralPath $licensePath -Destination (Join-Path $licensesRoot $licensePackages[$distribution])
}

curl.exe -L --fail --retry 3 --connect-timeout 30 --max-time 120 -o (Join-Path $licensesRoot 'ctranslate2.txt') https://raw.githubusercontent.com/OpenNMT/CTranslate2/v4.8.1/LICENSE
if ($LASTEXITCODE -ne 0) { throw 'Downloading the CTranslate2 license failed.' }
curl.exe -L --fail --retry 3 --connect-timeout 30 --max-time 120 -o (Join-Path $licensesRoot 'yt-dlp.txt') https://raw.githubusercontent.com/yt-dlp/yt-dlp/2026.08.19/LICENSE
if ($LASTEXITCODE -ne 0) { throw 'Downloading the yt-dlp license failed.' }
curl.exe -L --fail --retry 3 --connect-timeout 30 --max-time 120 -o (Join-Path $licensesRoot 'deno.txt') https://raw.githubusercontent.com/denoland/deno/v2.9.6/LICENSE.md
if ($LASTEXITCODE -ne 0) { throw 'Downloading the Deno license failed.' }

$sourceArchive = Join-Path $metadataRoot 'ffmpeg-source.zip'
Compress-Archive -Path (Join-Path $FfmpegSourceDirectory '*') -DestinationPath $sourceArchive -CompressionLevel Optimal
$pythonVersion = & $pythonExecutable -c 'import platform; print(platform.python_version())'
$ffmpegOutput = & (Join-Path $ffmpegBin 'ffmpeg.exe') -hide_banner -version
$versionMatch = [regex]::Match($ffmpegOutput[0], '^ffmpeg version ([^\s]+)')
if (-not $versionMatch.Success) { throw "Could not parse the FFmpeg version: $($ffmpegOutput[0])" }
$ffmpegVersion = $versionMatch.Groups[1].Value
$compilerLine = $ffmpegOutput | Select-String '^built with ' | Select-Object -First 1
if (-not $compilerLine) { throw 'Could not identify the compiler from FFmpeg version output.' }
$compiler = $compilerLine.Line.Replace('built with ', '')
$sourceArchiveSha256 = (Get-FileHash -LiteralPath $sourceArchive -Algorithm SHA256).Hash.ToLowerInvariant()

$build = [ordered]@{
    source_revision = 'n8.1.2'
    source_url      = 'https://ffmpeg.org/releases/ffmpeg-8.1.2.tar.xz'
    version         = $ffmpegVersion
    patches         = @()
    compiler        = $compiler
    configure       = $configure
    source_archive  = @{ path = 'ffmpeg-source.zip'; sha256 = $sourceArchiveSha256 }
}
$build | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $metadataRoot 'ffmpeg-build.json') -Encoding utf8

$licenseRecords = @(
    @{ path = 'LICENSES/python.txt'; spdx = 'PSF-2.0' },
    @{ path = 'LICENSES/ffmpeg.txt'; spdx = 'LGPL-2.1-or-later' },
    @{ path = 'LICENSES/pyav.txt'; spdx = 'BSD-3-Clause' },
    @{ path = 'LICENSES/faster-whisper.txt'; spdx = 'MIT' },
    @{ path = 'LICENSES/ctranslate2.txt'; spdx = 'MIT' },
    @{ path = 'LICENSES/numpy.txt'; spdx = 'BSD-3-Clause' },
    @{ path = 'LICENSES/better-profanity.txt'; spdx = 'MIT' },
    @{ path = 'LICENSES/huggingface-hub.txt'; spdx = 'Apache-2.0' },
    @{ path = 'LICENSES/yt-dlp.txt'; spdx = 'Unlicense' },
    @{ path = 'LICENSES/deno.txt'; spdx = 'MIT' }
)
$manifest = [ordered]@{
    schema_version = 1
    platform       = 'win32-x64'
    python         = @{ path = 'python/python.exe'; version = $pythonVersion; license = 'PSF-2.0' }
    ffmpeg         = @{ ffmpeg_path = 'ffmpeg/ffmpeg.exe'; ffprobe_path = 'ffmpeg/ffprobe.exe'; version = $ffmpegVersion; license = 'LGPL-2.1-or-later'; configure = $configure }
    pyav           = @{ version = '18.1.0'; license = 'BSD-3-Clause'; ffmpeg_library_origin = 'bundled-lgpl-build' }
    ytdlp          = @{ path = 'yt-dlp/yt-dlp.exe'; version = '2026.08.19'; source = 'https://github.com/yt-dlp/yt-dlp/releases/download/2026.08.19/yt-dlp.exe'; license = 'Unlicense' }
    deno           = @{ path = 'deno/deno.exe'; version = '2.9.6'; source = 'https://github.com/denoland/deno/releases/download/v2.9.6/deno-x86_64-pc-windows-msvc.zip'; license = 'MIT' }
    files          = @()
    licenses       = $licenseRecords
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $metadataRoot 'runtime-manifest.json') -Encoding utf8

$components = @(
    @{ name = 'Python'; version = $pythonVersion; license = 'PSF-2.0' },
    @{ name = 'FFmpeg'; version = $ffmpegVersion; license = 'LGPL-2.1-or-later' },
    @{ name = 'PyAV'; version = '18.1.0'; license = 'BSD-3-Clause' },
    @{ name = 'faster-whisper'; version = '1.2.1'; license = 'MIT' },
    @{ name = 'CTranslate2'; version = '4.8.1'; license = 'MIT' },
    @{ name = 'NumPy'; version = '2.5.2'; license = 'BSD-3-Clause' },
    @{ name = 'better-profanity'; version = '0.7.0'; license = 'MIT' },
    @{ name = 'huggingface-hub'; version = '1.28.0'; license = 'Apache-2.0' },
    @{ name = 'yt-dlp'; version = '2026.08.19'; license = 'Unlicense' },
    @{ name = 'Deno'; version = '2.9.6'; license = 'MIT' }
)
$sbomComponents = foreach ($component in $components) {
    @{ type = 'library'; name = $component.name; version = $component.version; licenses = @(@{ license = @{ id = $component.license } }) }
}
@{ bomFormat = 'CycloneDX'; specVersion = '1.5'; version = 1; components = $sbomComponents } |
ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $metadataRoot 'sbom.cdx.json') -Encoding utf8

$notices = $components | ForEach-Object { "- $($_.name) $($_.version) ($($_.license))" }
@('# Third-Party Notices', '', 'The bundled Windows runtime contains:', '', $notices) |
Set-Content -LiteralPath (Join-Path $metadataRoot 'THIRD_PARTY_NOTICES.md') -Encoding utf8

& (Join-Path $PSScriptRoot 'assemble-bundled-runtime.ps1') `
    -PythonRuntimeDirectory $pythonDirectory `
    -FfmpegDirectory $ffmpegBin `
    -YtdlpDirectory $ytdlpRoot `
    -DenoDirectory $denoRoot `
    -ReleaseMetadataDirectory $metadataRoot `
    -OutputDirectory $OutputDirectory
if ($LASTEXITCODE -ne 0) { throw 'Audited runtime assembly failed.' }