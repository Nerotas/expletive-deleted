param(
    [Parameter(Mandatory = $true)][string]$BinaryDirectory,
    [Parameter(Mandatory = $true)][string]$ScratchRoot
)

$ErrorActionPreference = 'Stop'
$ffmpeg = Join-Path $BinaryDirectory 'ffmpeg.exe'
$ffprobe = Join-Path $BinaryDirectory 'ffprobe.exe'
if (-not (Test-Path -LiteralPath $ffmpeg -PathType Leaf) -or
    -not (Test-Path -LiteralPath $ffprobe -PathType Leaf)) {
    throw 'The candidate directory must contain ffmpeg.exe and ffprobe.exe.'
}
if (-not (Test-Path -LiteralPath $ScratchRoot -PathType Container)) {
    throw 'ScratchRoot must be an existing directory.'
}

# Use a fresh child so -y can never overwrite media supplied by the caller.
$probeDirectory = Join-Path $ScratchRoot ('ffmpeg-smoke-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $probeDirectory | Out-Null
$source = Join-Path $probeDirectory 'source.mp4'
$h264 = Join-Path $probeDirectory 'h264.mp4'
$muted = Join-Path $probeDirectory 'muted.mp4'
$mp3 = Join-Path $probeDirectory 'muted.mp3'

function Invoke-FFmpeg([string[]]$Arguments) {
    & $ffmpeg -nostdin -hide_banner -loglevel error -y @Arguments
    if ($LASTEXITCODE -ne 0) { throw "FFmpeg exited $LASTEXITCODE." }
}

function Get-Codec([string]$Path, [string]$Stream) {
    $result = & $ffprobe -v error -select_streams $Stream -show_entries stream=codec_name `
        -of 'default=nokey=1:noprint_wrappers=1' $Path
    if ($LASTEXITCODE -ne 0) { throw "FFprobe exited $LASTEXITCODE for $Path." }
    return ($result | Out-String).Trim()
}

function Get-VideoHash([string]$Path) {
    $result = & $ffmpeg -nostdin -v error -i $Path -map '0:v:0' -f hash -hash sha256 -
    if ($LASTEXITCODE -ne 0) { throw "Video hash failed for $Path." }
    return ($result | Out-String).Trim()
}

Invoke-FFmpeg @('-f', 'lavfi', '-i', 'testsrc2=size=128x72:rate=24',
    '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=44100',
    '-t', '1', '-c:v', 'mpeg4', '-c:a', 'aac', '-shortest', $source)
$sourceFileHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
Invoke-FFmpeg @('-i', $source, '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', $h264)
if ((Get-Codec $h264 'v:0') -ne 'h264' -or (Get-Codec $h264 'a:0') -ne 'aac') {
    throw 'The forced libx264/AAC conversion has unexpected codecs.'
}

Invoke-FFmpeg @('-i', $h264, '-af', "volume=0:enable='between(t,0.25,0.75)'",
    '-c:v', 'copy', '-c:a', 'aac', $muted)
if ((Get-Codec $muted 'v:0') -ne 'h264' -or
    (Get-VideoHash $h264) -ne (Get-VideoHash $muted)) {
    throw 'Preserve-source processing changed the copied video stream.'
}

Invoke-FFmpeg @('-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=44100',
    '-t', '1', '-af', "volume=0:enable='between(t,0.25,0.75)'",
    '-c:a', 'libmp3lame', '-q:a', '4', $mp3)
if ((Get-Codec $mp3 'a:0') -ne 'mp3') { throw 'The muted audio output is not MP3.' }
if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ne $sourceFileHash) {
    throw 'The synthetic source was modified.'
}

Write-Output "PASS: H.264/AAC, MP3, preserve-source video, and source integrity; $probeDirectory"
