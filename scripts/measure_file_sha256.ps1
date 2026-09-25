#requires -Version 5.1
<#
.SYNOPSIS
Measure the time to read and SHA-256 hash one complete file.
.DESCRIPTION
Opens the selected file read-only and prints results. Does not write sidecars,
change transcripts, install software, or run transcription. A network path will
read from that network location. Memory use is bounded rather than file-sized.

The timer includes opening, reading, hashing, and closing the file. Results measure
this PowerShell/.NET implementation, not a promised application processing time.
Windows may cache file reads, including before the first run. Repeated runs can
therefore be faster; this script does not flush caches. Compare representative
local and external-drive files under normal conditions and note their locations.
.PARAMETER Path
Literal path to a file. Spaces and wildcard characters are treated literally.
.PARAMETER Runs
Number of complete reads to measure separately. Defaults to one.
.EXAMPLE
.\scripts\measure_file_sha256.ps1 -Path 'E:\Movies\Feature Film.mkv'
.EXAMPLE
.\scripts\measure_file_sha256.ps1 -Path 'E:\Movies\Feature Film.mkv' -Runs 3
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory, Position = 0)]
    [ValidateNotNullOrEmpty()]
    [string]$Path,

    [ValidateRange(1, 20)]
    [int]$Runs = 1
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$item = Get-Item -LiteralPath $Path -Force
if ($item -isnot [System.IO.FileInfo]) {
    throw 'Choose a file, not a directory or another provider item.'
}
$filePath = $item.FullName

Write-Host 'Full-file SHA-256 benchmark; media is opened read-only.'
Write-Host 'Cached reads may be faster. Each run reads the entire file; no transcription runs.'

for ($run = 1; $run -le $Runs; $run++) {
    Write-Host "Hashing run $run of $Runs ..."
    $stream = $null
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    $timer = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        # Allow other readers, but deny ordinary writes/deletion during this read.
        $stream = [System.IO.FileStream]::new(
            $filePath,
            [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::Read,
            [System.IO.FileShare]::Read,
            1MB,
            [System.IO.FileOptions]::SequentialScan
        )
        $sizeBytes = $stream.Length
        $hashBytes = $sha256.ComputeHash($stream)
    }
    catch {
        throw "Could not hash the file. Check its availability, read permissions, and whether another program has it open for writing. $($_.Exception.Message)"
    }
    finally {
        if ($null -ne $stream) { $stream.Dispose() }
        $timer.Stop()
        $sha256.Dispose()
    }

    [pscustomobject]@{
        File = $filePath
        Run = $run
        SizeBytes = $sizeBytes
        SizeGiB = [Math]::Round($sizeBytes / 1GB, 3)
        Seconds = [Math]::Round($timer.Elapsed.TotalSeconds, 6)
        MiBPerSecond = [Math]::Round(($sizeBytes / 1MB) / [Math]::Max($timer.Elapsed.TotalSeconds, 0.000000001), 2)
        SHA256 = [BitConverter]::ToString($hashBytes).Replace('-', '').ToLowerInvariant()
    }
}
