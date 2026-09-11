[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$PythonRuntimeDirectory,

    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$OutputDirectory
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$pythonDirectory = [IO.Path]::GetFullPath($PythonRuntimeDirectory)
$pythonExecutable = Join-Path $pythonDirectory 'python.exe'
$temporaryBase = if ([string]::IsNullOrWhiteSpace($env:RUNNER_TEMP)) {
    [IO.Path]::GetTempPath()
} else {
    $env:RUNNER_TEMP
}
$workRoot = Join-Path $temporaryBase 'audited-python-runtime-build'
$metadataRoot = Join-Path $workRoot 'metadata'
$licensesRoot = Join-Path $metadataRoot 'LICENSES'
$buildInputs = Get-Content -LiteralPath (Join-Path $PSScriptRoot '..\runtime\windows-x64\build-inputs.json') -Raw | ConvertFrom-Json

foreach ($path in @($pythonExecutable, (Join-Path $pythonDirectory 'LICENSE.txt'))) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Required private Python input is missing: $path"
    }
}

if (Test-Path -LiteralPath $workRoot) {
    Remove-Item -LiteralPath $workRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $workRoot, $metadataRoot, $licensesRoot -Force | Out-Null

$pythonVersion = (& $pythonExecutable -I -c 'import platform; print(platform.python_version())').Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($pythonVersion)) {
    throw 'Could not determine the private Python version.'
}
if ($pythonVersion -ne $buildInputs.python.version) {
    throw "Private Python version $pythonVersion does not match the approved $($buildInputs.python.version)."
}
$pipVersion = (& $pythonExecutable -I -c "import importlib.metadata as m; print(m.version('pip'))").Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($pipVersion)) {
    throw 'The private Python runtime must include pip for approved first-run setup.'
}
if ($pipVersion -ne $buildInputs.pip.version) {
    throw "Private pip version $pipVersion does not match the approved $($buildInputs.pip.version)."
}
$pipLicensePath = (& $pythonExecutable -I -c "import importlib.metadata as m; d=m.distribution('pip'); files=[f for f in d.files or () if str(f).replace(chr(92), '/').lower().endswith('/license.txt')]; print(d.locate_file(files[0]) if files else '')").Trim()
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $pipLicensePath)) {
    throw 'The private Python runtime is missing the pip license text.'
}

Copy-Item -LiteralPath (Join-Path $pythonDirectory 'LICENSE.txt') -Destination (Join-Path $licensesRoot 'python.txt')
Copy-Item -LiteralPath $pipLicensePath -Destination (Join-Path $licensesRoot 'pip.txt')

$licenseRecords = @(
    @{ path = 'LICENSES/python.txt'; spdx = 'PSF-2.0' },
    @{ path = 'LICENSES/pip.txt'; spdx = 'MIT' }
)
$manifest = [ordered]@{
    schema_version = 2
    platform       = 'win32-x64'
    python         = @{ path = 'python/python.exe'; version = $pythonVersion; license = 'PSF-2.0' }
    pip            = @{ version = $pipVersion; license = 'MIT' }
    files          = @()
    licenses       = $licenseRecords
}
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $metadataRoot 'runtime-manifest.json') -Encoding utf8

$components = @(
    @{ name = 'Python'; version = $pythonVersion; license = 'PSF-2.0' },
    @{ name = 'pip'; version = $pipVersion; license = 'MIT' }
)
$sbomComponents = foreach ($component in $components) {
    @{ type = 'application'; name = $component.name; version = $component.version; licenses = @(@{ license = @{ id = $component.license } }) }
}
@{ bomFormat = 'CycloneDX'; specVersion = '1.5'; version = 1; components = $sbomComponents } |
ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $metadataRoot 'sbom.cdx.json') -Encoding utf8

@(
    '# Third-Party Notices',
    '',
    'The Windows installer includes only the private Python bootstrap runtime:',
    '',
    "- Python $pythonVersion (PSF-2.0)",
    "- pip $pipVersion (MIT)",
    '',
    'Processing packages, media tools, and speech models are obtained only after user approval.'
) | Set-Content -LiteralPath (Join-Path $metadataRoot 'THIRD_PARTY_NOTICES.md') -Encoding utf8

& (Join-Path $PSScriptRoot 'assemble-bundled-runtime.ps1') `
    -PythonRuntimeDirectory $pythonDirectory `
    -ReleaseMetadataDirectory $metadataRoot `
    -OutputDirectory $OutputDirectory
if ($LASTEXITCODE -ne 0) { throw 'Private Python runtime assembly failed.' }
