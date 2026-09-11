[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$PythonRuntimeDirectory,

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
$metadataRoot = [IO.Path]::GetFullPath($ReleaseMetadataDirectory)
$outputRoot = [IO.Path]::GetFullPath($OutputDirectory)
$temporaryRoot = "$outputRoot.partial"

Require-Path (Join-Path $pythonRuntime 'python.exe') 'Private Python executable'
foreach ($name in @('THIRD_PARTY_NOTICES.md', 'LICENSES', 'sbom.cdx.json', 'runtime-manifest.json')) {
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
    $pythonDestination = Join-Path $temporaryRoot 'python'
    Copy-Item -LiteralPath $pythonRuntime -Destination $pythonDestination -Recurse

    # Retain the installed, audited pip while excluding CPython's bootstrap
    # wheel cache and test fixtures from the distributable runtime.
    foreach ($relativePath in @('Lib\ensurepip', 'Lib\test')) {
        $excludedPath = Join-Path $pythonDestination $relativePath
        if (Test-Path -LiteralPath $excludedPath) {
            Remove-Item -LiteralPath $excludedPath -Recurse -Force
        }
    }

    foreach ($name in @('THIRD_PARTY_NOTICES.md', 'LICENSES', 'sbom.cdx.json', 'runtime-manifest.json')) {
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
    Write-Host "Assembled and verified private Python runtime: $outputRoot"
}
catch {
    Write-Error "Private Python runtime assembly did not publish a payload. Inspect the retained partial directory: $temporaryRoot"
    throw
}
