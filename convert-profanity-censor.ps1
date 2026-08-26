[CmdletBinding()]
param(
    [ValidateSet('large')]
    [string]$Model = 'large',
    [switch]$List,
    [switch]$ReportOnly,
    [switch]$Overwrite,
    [switch]$IncludeUndiscovered
)

$ProjectRoot = Split-Path -Parent $PSCommandPath
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$BatchScript = Join-Path $ProjectRoot 'batch_process.py'

if (-not (Test-Path $Python)) {
    Write-Error "Local virtual environment not found. Run: python setup.py"
    exit 1
}

$Arguments = @($BatchScript, '--model', $Model)
if ($List) {
    $Arguments += '--list'
}
if ($ReportOnly) {
    $Arguments += '--report-only'
}
if ($Overwrite) {
    $Arguments += '--overwrite'
}
if ($IncludeUndiscovered) {
    $Arguments += '--include-undiscovered'
}

& $Python @Arguments
exit $LASTEXITCODE