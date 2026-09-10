[CmdletBinding()]
param(
    [switch]$SkipPackaged
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$frontendRoot = Join-Path $repositoryRoot 'frontend'
$python = Join-Path $repositoryRoot '.venv\Scripts\python.exe'
$failures = [System.Collections.Generic.List[string]]::new()

function Invoke-TestStage([string]$Name, [scriptblock]$Action) {
    Write-Host "`n=== $Name ===" -ForegroundColor Cyan
    try {
        & $Action
        if ($LASTEXITCODE -ne 0) {
            throw "exit code $LASTEXITCODE"
        }
    }
    catch {
        $failures.Add("${Name}: $($_.Exception.Message)")
        Write-Host "FAILED: $Name" -ForegroundColor Red
    }
}

if (-not (Test-Path -LiteralPath $python)) {
    throw "Repository Python environment was not found at $python. Run python setup.py first."
}

Push-Location $repositoryRoot
try {
    Invoke-TestStage 'Backend tests' {
        & $python -m unittest discover -s tests -q
    }

    Push-Location $frontendRoot
    try {
        Invoke-TestStage 'Frontend tests' { npm test }
        Invoke-TestStage 'Frontend typecheck' { npm run typecheck }
        Invoke-TestStage 'Frontend lint' { npm run lint }
        Invoke-TestStage 'Development Electron smoke' { npm run smoke }

        if (-not $SkipPackaged) {
            Invoke-TestStage 'Setup-first package build and audit' { npm run package:dir }
            Invoke-TestStage 'Setup-first packaged smoke' { npm run smoke:package }
        }
    }
    finally {
        Pop-Location
    }
}
finally {
    Pop-Location
}

if ($failures.Count -gt 0) {
    Write-Host "`nValidation completed with failures:" -ForegroundColor Red
    $failures | ForEach-Object { Write-Host "- $_" -ForegroundColor Red }
    exit 1
}

Write-Host "`nAll requested tests passed." -ForegroundColor Green
