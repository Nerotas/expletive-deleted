[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$OutputDirectory,

    [string]$ArchivePath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$inputs = Get-Content -LiteralPath (Join-Path $PSScriptRoot '..\runtime\windows-x64\build-inputs.json') -Raw | ConvertFrom-Json
$destination = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $destination) {
    throw "Pinned Python destination already exists: $destination"
}

$downloadedArchive = $false
if ([string]::IsNullOrWhiteSpace($ArchivePath)) {
    $ArchivePath = "$destination.zip"
    if (Test-Path -LiteralPath $ArchivePath) {
        throw "Pinned Python archive path already exists: $ArchivePath"
    }
    Invoke-WebRequest -Uri $inputs.python.source_url -OutFile $ArchivePath -UseBasicParsing
    $downloadedArchive = $true
}

$actualHash = (Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -ne $inputs.python.sha256) {
    throw "Pinned Python archive SHA-256 mismatch. Expected $($inputs.python.sha256), got $actualHash."
}

Expand-Archive -LiteralPath $ArchivePath -DestinationPath $destination
$python = Join-Path $destination 'python.exe'
$version = (& $python -I -c 'import platform; print(platform.python_version())').Trim()
if ($LASTEXITCODE -ne 0 -or $version -ne $inputs.python.version) {
    throw "Pinned Python runtime version mismatch: $version"
}
$pipVersion = (& $python -I -c 'import pip; print(pip.__version__)').Trim()
if ($LASTEXITCODE -ne 0 -or $pipVersion -ne $inputs.pip.version) {
    throw "Pinned Python pip version mismatch: $pipVersion"
}
if (-not (Test-Path -LiteralPath (Join-Path $destination 'LICENSE.txt') -PathType Leaf)) {
    throw 'Pinned Python runtime is missing LICENSE.txt.'
}

if ($downloadedArchive) {
    Remove-Item -LiteralPath $ArchivePath
}
Write-Host "Verified pinned Python $version with pip ${pipVersion}: $destination"
