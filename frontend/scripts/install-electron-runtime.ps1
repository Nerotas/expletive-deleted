<#
.SYNOPSIS
Installs Electron's Windows runtime without loading Electron's native ZIP extractor.

.DESCRIPTION
Some Windows Application Control policies block Electron's native extractor during
`npm install`. This script downloads the exact Electron release declared in
node_modules/electron, verifies its SHA-256 against Electron's bundled checksum
manifest, then expands it with PowerShell.
#>

$ErrorActionPreference = 'Stop'

$frontendRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$electronRoot = Join-Path $frontendRoot 'node_modules\electron'
$packagePath = Join-Path $electronRoot 'package.json'
$checksumsPath = Join-Path $electronRoot 'checksums.json'

if (-not (Test-Path $packagePath) -or -not (Test-Path $checksumsPath)) {
    throw 'Electron package files are missing. Run npm install first; this script repairs only the blocked Electron runtime download.'
}

$version = (Get-Content $packagePath -Raw | ConvertFrom-Json).version
$architecture = (& node -p 'process.arch').Trim()
if ($architecture -notin @('x64', 'arm64')) {
    throw "Unsupported Windows Node architecture: $architecture"
}

$asset = "electron-v$version-win32-$architecture.zip"
$checksums = Get-Content $checksumsPath -Raw | ConvertFrom-Json
$expectedHash = $checksums.PSObject.Properties[$asset].Value
if (-not $expectedHash) {
    throw "Electron checksum manifest does not include $asset"
}

$archivePath = Join-Path ([System.IO.Path]::GetTempPath()) $asset
$downloadUrl = "https://github.com/electron/electron/releases/download/v$version/$asset"
Write-Host "Downloading Electron $version for Windows $architecture..."
Invoke-WebRequest -Uri $downloadUrl -OutFile $archivePath

$actualHash = (Get-FileHash -Algorithm SHA256 $archivePath).Hash.ToLowerInvariant()
if ($actualHash -ne $expectedHash.ToLowerInvariant()) {
    throw "Electron download checksum mismatch. Expected $expectedHash, got $actualHash."
}

$runtimePath = Join-Path $electronRoot 'dist'
if (Test-Path $runtimePath) {
    Remove-Item -Recurse -Force $runtimePath
}
Expand-Archive -Path $archivePath -DestinationPath $runtimePath -Force
Set-Content -Path (Join-Path $electronRoot 'path.txt') -Value 'electron.exe' -NoNewline

$electronExecutable = Join-Path $runtimePath 'electron.exe'
if (-not (Test-Path $electronExecutable)) {
    throw "Electron runtime extraction did not produce $electronExecutable"
}

Write-Host "Electron runtime installed and verified: $electronExecutable"
