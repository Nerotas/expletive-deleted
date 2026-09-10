[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$PythonRuntimeDirectory,

    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$FfmpegDirectory,

    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$YtdlpDirectory,

    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$DenoDirectory,

    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$ReleaseMetadataDirectory,

    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$OutputDirectory
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Require-Path([string]$Path, [string]$Description) {
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "$Description was not found: $Path"
    }
}

$frontendRoot = Split-Path -Parent $PSScriptRoot
$pythonRuntime = [IO.Path]::GetFullPath($PythonRuntimeDirectory)
$ffmpegRuntime = [IO.Path]::GetFullPath($FfmpegDirectory)
$ytdlpRuntime = [IO.Path]::GetFullPath($YtdlpDirectory)
$denoRuntime = [IO.Path]::GetFullPath($DenoDirectory)
$metadataRoot = [IO.Path]::GetFullPath($ReleaseMetadataDirectory)
$outputRoot = [IO.Path]::GetFullPath($OutputDirectory)
$temporaryRoot = "$outputRoot.partial"

Require-Path (Join-Path $pythonRuntime 'python.exe') 'Private Python executable'
Require-Path (Join-Path $ffmpegRuntime 'ffmpeg.exe') 'Approved FFmpeg executable'
Require-Path (Join-Path $ffmpegRuntime 'ffprobe.exe') 'Approved FFprobe executable'
Require-Path (Join-Path $ytdlpRuntime 'yt-dlp.exe') 'Approved yt-dlp executable'
Require-Path (Join-Path $denoRuntime 'deno.exe') 'Approved Deno executable'
foreach ($name in @('THIRD_PARTY_NOTICES.md', 'LICENSES', 'sbom.cdx.json', 'ffmpeg-source.zip', 'ffmpeg-build.json', 'runtime-manifest.json')) {
    Require-Path (Join-Path $metadataRoot $name) "Release metadata $name"
}
if (Test-Path -LiteralPath $outputRoot) {
    throw "Refusing to replace an existing runtime payload: $outputRoot"
}
if (Test-Path -LiteralPath $temporaryRoot) {
    throw "Remove or inspect the prior incomplete build directory before retrying: $temporaryRoot"
}

New-Item -ItemType Directory -Path $temporaryRoot | Out-Null
try {
    Copy-Item -LiteralPath $pythonRuntime -Destination (Join-Path $temporaryRoot 'python') -Recurse
    Copy-Item -LiteralPath $ffmpegRuntime -Destination (Join-Path $temporaryRoot 'ffmpeg') -Recurse
    New-Item -ItemType Directory -Path (Join-Path $temporaryRoot 'yt-dlp') | Out-Null
    Copy-Item -LiteralPath (Join-Path $ytdlpRuntime 'yt-dlp.exe') -Destination (Join-Path $temporaryRoot 'yt-dlp' 'yt-dlp.exe')
    New-Item -ItemType Directory -Path (Join-Path $temporaryRoot 'deno') | Out-Null
    Copy-Item -LiteralPath (Join-Path $denoRuntime 'deno.exe') -Destination (Join-Path $temporaryRoot 'deno' 'deno.exe')
    foreach ($name in @('THIRD_PARTY_NOTICES.md', 'LICENSES', 'sbom.cdx.json', 'ffmpeg-source.zip', 'ffmpeg-build.json', 'runtime-manifest.json')) {
        Copy-Item -LiteralPath (Join-Path $metadataRoot $name) -Destination (Join-Path $temporaryRoot $name) -Recurse
    }

    Push-Location $frontendRoot
    try {
        & node scripts/generate-bundled-runtime-manifest.mjs $temporaryRoot
        if ($LASTEXITCODE -ne 0) { throw 'Runtime manifest generation failed.' }
        & node scripts/audit-bundled-runtime.mjs $temporaryRoot
        if ($LASTEXITCODE -ne 0) { throw 'Runtime artifact audit failed.' }
        & node scripts/verify-bundled-runtime.mjs $temporaryRoot
        if ($LASTEXITCODE -ne 0) { throw 'Runtime executable verification failed.' }
    }
    finally {
        Pop-Location
    }

    Move-Item -LiteralPath $temporaryRoot -Destination $outputRoot
    Write-Host "Assembled and verified bundled runtime: $outputRoot"
}
catch {
    Write-Error "Bundled runtime assembly did not publish a payload. Inspect the retained partial directory: $temporaryRoot"
    throw
}
