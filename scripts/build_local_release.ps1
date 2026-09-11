[CmdletBinding()]
param(
    [string]$PythonExecutable,
    [switch]$KeepWorkDirectory
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$requiredNodeVersion = '22.12.0'
$requiredPythonVersion = '3.13.15'
$requiredPipVersion = '25.2'
$pythonArchiveUrl = 'https://www.python.org/ftp/python/3.13.15/python-3.13.15-amd64.zip'
$pythonArchiveSha256 = '6479223746cdfb79d25865110d6f524ac98de081324e119af1dc3ae36bddc7a5'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$frontendRoot = Join-Path $repositoryRoot 'frontend'
$workRoot = Join-Path (Join-Path $frontendRoot 'release') ".local-build-$([guid]::NewGuid())"
$nativeTemporaryRoot = Join-Path $workRoot 'temp'
$privatePythonRoot = Join-Path $workRoot 'private-python'
$testEnvironmentRoot = Join-Path $workRoot 'test-venv'
$auditedRuntimeRoot = Join-Path $workRoot 'audited-runtime'
$succeeded = $false
$offlineEnvironmentSnapshots = @()

function Assert-NativeSuccess([string]$Description) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE."
    }
}

function Get-PythonVersion([string]$Executable) {
    $version = (& $Executable -I -c 'import platform; print(platform.python_version())').Trim()
    Assert-NativeSuccess 'Reading the Python version'
    return $version
}

function Find-ApprovedPython {
    if (-not [string]::IsNullOrWhiteSpace($PythonExecutable)) {
        if (-not (Test-Path -LiteralPath $PythonExecutable -PathType Leaf)) {
            throw "Python executable was not found: $PythonExecutable"
        }
        return (Resolve-Path -LiteralPath $PythonExecutable).Path
    }

    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($null -ne $launcher) {
        $candidate = (& $launcher.Source -3.13 -c 'import sys; print(sys.executable)' 2>$null)
        if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($candidate)) {
            $candidate = $candidate.Trim()
            if ((Get-PythonVersion $candidate) -eq $requiredPythonVersion) {
                return $candidate
            }
        }
    }

    foreach ($commandName in @('python', 'python3')) {
        $command = Get-Command $commandName -ErrorAction SilentlyContinue
        if ($null -ne $command -and (Get-PythonVersion $command.Source) -eq $requiredPythonVersion) {
            return $command.Source
        }
    }

    $archivePath = Join-Path $workRoot "python-$requiredPythonVersion-amd64.zip"
    $downloadedPythonRoot = Join-Path $workRoot "python-$requiredPythonVersion-amd64"
    Write-Host "Python $requiredPythonVersion was not found; downloading the official x64 runtime..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri $pythonArchiveUrl -OutFile $archivePath -UseBasicParsing
    $actualHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $pythonArchiveSha256) {
        throw "Downloaded Python archive SHA-256 mismatch. Expected $pythonArchiveSha256, got $actualHash."
    }
    Expand-Archive -LiteralPath $archivePath -DestinationPath $downloadedPythonRoot

    $downloadedPython = Join-Path $downloadedPythonRoot 'python.exe'
    if ((Get-PythonVersion $downloadedPython) -ne $requiredPythonVersion) {
        throw "The verified Python archive did not contain Python $requiredPythonVersion."
    }
    return $downloadedPython
}

function Save-EnvironmentVariable([string]$Name) {
    return [pscustomobject]@{
        Name = $Name
        Exists = Test-Path -LiteralPath "Env:$Name"
        Value = [Environment]::GetEnvironmentVariable($Name, 'Process')
    }
}

function Restore-EnvironmentVariable($Snapshot) {
    if ($Snapshot.Exists) {
        [Environment]::SetEnvironmentVariable($Snapshot.Name, $Snapshot.Value, 'Process')
    }
    else {
        [Environment]::SetEnvironmentVariable($Snapshot.Name, $null, 'Process')
    }
}

Push-Location $repositoryRoot
try {
    $nodeVersion = (& node --version).TrimStart('v')
    Assert-NativeSuccess 'Reading the Node.js version'
    if ([version]$nodeVersion -lt [version]$requiredNodeVersion) {
        throw "Local releases require Node.js $requiredNodeVersion or later, but this shell is using $nodeVersion."
    }

    $nodePlatform = (& node -p '`${process.platform}-${process.arch}`').Trim()
    Assert-NativeSuccess 'Reading the Node.js platform'
    if ($nodePlatform -ne 'win32-x64') {
        throw "Local Windows releases require win32-x64 Node.js; found $nodePlatform."
    }

    $worktreeStatus = @(& git status --porcelain --untracked-files=normal)
    Assert-NativeSuccess 'Checking the Git worktree'
    if ($worktreeStatus.Count -gt 0) {
        Write-Warning 'The worktree has local changes. This installer will include them and may differ from a GitHub release built from committed source.'
    }

    Write-Host "Building release-equivalent installer from $(git rev-parse --short HEAD)" -ForegroundColor Cyan
    Write-Host "Temporary build directory: $workRoot"
    New-Item -ItemType Directory -Path $workRoot, $nativeTemporaryRoot | Out-Null

    $approvedPython = Find-ApprovedPython
    $pythonVersion = Get-PythonVersion $approvedPython
    if ($pythonVersion -ne $requiredPythonVersion) {
        throw "GitHub releases use Python $requiredPythonVersion, but $approvedPython is Python $pythonVersion."
    }

    $offlineEnvironmentSnapshots = @(
        Save-EnvironmentVariable 'HF_HUB_OFFLINE'
        Save-EnvironmentVariable 'PIP_DISABLE_PIP_VERSION_CHECK'
        Save-EnvironmentVariable 'TEMP'
        Save-EnvironmentVariable 'TMP'
    )
    $env:HF_HUB_OFFLINE = '1'
    $env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
    $env:TEMP = $nativeTemporaryRoot
    $env:TMP = $nativeTemporaryRoot

    $pythonSourceRoot = (& $approvedPython -I -c 'import sys; print(sys.prefix)').Trim()
    Assert-NativeSuccess 'Locating the Python installation'
    Copy-Item -LiteralPath $pythonSourceRoot -Destination $privatePythonRoot -Recurse

    $privatePython = Join-Path $privatePythonRoot 'python.exe'
    if (-not (Test-Path -LiteralPath $privatePython -PathType Leaf)) {
        throw "The copied Python runtime is missing python.exe: $privatePythonRoot"
    }

    # Pin pip inside the copy so the user's Python installation is not modified.
    if (-not (Test-Path -LiteralPath (Join-Path $privatePythonRoot 'Lib\site-packages\pip'))) {
        & $privatePython -I -m ensurepip --default-pip
        Assert-NativeSuccess 'Bootstrapping pip in the private Python runtime'
    }
    & $privatePython -I -m pip install --disable-pip-version-check --upgrade "pip==$requiredPipVersion"
    Assert-NativeSuccess 'Pinning pip in the private Python runtime'

    $copiedPrefix = (& $privatePython -I -c 'import sys; print(sys.prefix)').Trim()
    Assert-NativeSuccess 'Verifying the copied Python runtime'
    if ([IO.Path]::GetFullPath($copiedPrefix) -ne [IO.Path]::GetFullPath($privatePythonRoot)) {
        throw "The copied Python runtime is not relocatable: $copiedPrefix"
    }

    & $approvedPython -m venv $testEnvironmentRoot
    Assert-NativeSuccess 'Creating the backend test environment'
    $testPython = Join-Path $testEnvironmentRoot 'Scripts\python.exe'
    & $testPython -m pip install --disable-pip-version-check --upgrade "pip==$requiredPipVersion"
    Assert-NativeSuccess 'Pinning pip in the backend test environment'
    & $testPython -m pip install --disable-pip-version-check -r (Join-Path $repositoryRoot 'requirements.txt')
    Assert-NativeSuccess 'Installing backend dependencies'
    & $testPython -m unittest discover -s tests
    Assert-NativeSuccess 'Backend tests'

    Push-Location $frontendRoot
    try {
        & npm ci
        Assert-NativeSuccess 'Installing frontend dependencies'
        & npm run version:check
        Assert-NativeSuccess 'Version metadata check'
        & npm test
        Assert-NativeSuccess 'Frontend tests'
        & npm run typecheck
        Assert-NativeSuccess 'Frontend typecheck'
        & npm run lint
        Assert-NativeSuccess 'Frontend lint'
        & npm run smoke
        Assert-NativeSuccess 'Development Electron smoke test'

        & (Join-Path $frontendRoot 'scripts\build-audited-runtime.ps1') `
            -PythonRuntimeDirectory $privatePythonRoot `
            -OutputDirectory $auditedRuntimeRoot

        $environmentSnapshots = @(
            Save-EnvironmentVariable 'BUNDLED_RUNTIME_DIR'
            Save-EnvironmentVariable 'REQUIRE_BUNDLED_RUNTIME'
        )
        try {
            $env:BUNDLED_RUNTIME_DIR = $auditedRuntimeRoot
            $env:REQUIRE_BUNDLED_RUNTIME = '1'

            & npm run package:win
            Assert-NativeSuccess 'Windows installer build and audit'
            & npm run smoke:setup-first-package
            Assert-NativeSuccess 'Packaged application smoke test'
        }
        finally {
            foreach ($snapshot in $environmentSnapshots) {
                Restore-EnvironmentVariable $snapshot
            }
        }
    }
    finally {
        Pop-Location
    }

    $package = Get-Content -LiteralPath (Join-Path $frontendRoot 'package.json') -Raw | ConvertFrom-Json
    $installer = Join-Path $frontendRoot "release\Expletive-Deleted-Setup-$($package.version)-x64.exe"
    if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) {
        throw "The installer was not created at the expected path: $installer"
    }

    $succeeded = $true
    Write-Host "`nProduction installer created and verified:" -ForegroundColor Green
    Write-Host $installer
}
finally {
    Pop-Location
    foreach ($snapshot in $offlineEnvironmentSnapshots) {
        Restore-EnvironmentVariable $snapshot
    }
    if ($succeeded -and -not $KeepWorkDirectory -and (Test-Path -LiteralPath $workRoot)) {
        try {
            Remove-Item -LiteralPath $workRoot -Recurse -Force
        }
        catch {
            Write-Warning "The installer passed, but its temporary build directory could not be removed: $workRoot"
        }
    }
    elseif ((Test-Path -LiteralPath $workRoot)) {
        Write-Host "Build files retained for inspection: $workRoot" -ForegroundColor Yellow
    }
}
