# Troubleshooting Guide - Profanity Censoring Workflow

## Quick Reference

| Problem | Solution | Priority |
|---------|----------|----------|
| FFmpeg not found | Install FFmpeg, add to PATH, restart | 🔴 Critical |
| Python module not found | Run `pip install [package]` | 🔴 Critical |
| Out of memory | Close applications, increase virtual memory, or split the media file | 🟡 High |
| Slow processing | Enable NVIDIA GPU acceleration | 🟢 Low |
| File access denied | Check file permissions | 🔴 Critical |
| No output file created | Check input format with ffprobe | 🟡 High |
| Whisper can't parse audio | Extract audio with ffmpeg first | 🟡 High |
| Filter syntax errors | Verify FFmpeg version (4.0+) | 🟡 High |

---

## Problem: "FFmpeg not found"

### Error Message
```
[-] FFmpeg not found at C:\ffmpeg\bin\ffmpeg.exe
```

### Causes
- FFmpeg not installed
- Not added to PATH
- Wrong installation path
- PowerShell not restarted after PATH change

### Solutions

**Option 1: Install FFmpeg (Recommended)**
1. Download: https://www.gyan.dev/ffmpeg/builds/
2. Click "full" → download (50-100MB)
3. Extract to `C:\ffmpeg`
4. Add to PATH:
   - `Win + R` → `sysdm.cpl`
   - Environment Variables → New
   - Variable name: `Path`
   - Variable value: `C:\ffmpeg\bin`
5. **Restart PowerShell**
6. Test: `ffmpeg -version`

**Option 2: Verify Existing Installation**
```powershell
# Find FFmpeg
where ffmpeg

# Test version
ffmpeg -version

# Add to PATH if needed
$env:Path = "C:\ffmpeg\bin;$env:Path"
```

**Option 3: Use Chocolatey (Windows)**
```powershell
# Install Chocolatey first if needed
choco install ffmpeg
```

---

## Problem: "Python module not found"

### Error Messages
```
ModuleNotFoundError: No module named 'whisper'
ModuleNotFoundError: No module named 'better_profanity'
```

### Solutions

**Option 1: Use Setup Script (Recommended)**
```powershell
python setup.py
```

**Option 2: Manual Installation**
```powershell
# Install all packages
pip install faster-whisper better-profanity numpy

# Or individually:
pip install faster-whisper
pip install better-profanity
pip install numpy
```

**Option 3: Verify Installation**
```powershell
# Check each package
python -c "from faster_whisper import WhisperModel; print('faster-whisper OK')"
python -c "import better_profanity; print('better-profanity OK')"
python -c "import numpy; print('NumPy OK')"
```

**Option 4: Multiple Python Versions**
If you have multiple Python versions:
```powershell
# Use specific Python version
C:\Python39\Scripts\pip install faster-whisper

# Or specify when running
C:\Python39\python.exe censor_profanity.py input.mp4 output.mp4
```

---

## Problem: "Out of memory" or "MemoryError"

### Error Messages
```
MemoryError: Unable to allocate X.XX GiB
```

### Causes
- Using large Whisper model with limited RAM
- Processing very long audio files
- Other applications consuming memory

### Solutions

Whisper `large-v3` is required for the word-level timestamp accuracy used by censorship. Do not switch to a smaller model.

**Option 1: Close Other Applications**
- Close browsers, video players, heavy applications
- Disable non-essential services
- Check Task Manager for memory-hogging processes

**Option 2: Increase Virtual Memory**
```powershell
# Windows: Adjust page file size
# Settings → System → About → Advanced system settings
# → Advanced → Virtual Memory → Change
# Set to: Initial = 4GB, Maximum = 16GB
```

**Option 3: Split Large Files**
```powershell
# Process first hour only
ffmpeg -i large_file.mp4 -t 3600 first_hour.mp4

python censor_profanity.py first_hour.mp4 output.mp4
```

---

## Problem: "Slow processing"

### Causes
- Using the large Whisper model on CPU
- Slow disk I/O
- Multiple other processes running

### Solutions

Whisper `large-v3` is required for censorship timing. To improve throughput, use the automatically selected supported GPU profile, reduce competing system load, or process files sequentially.

**Option 3: Process Multiple Files in Parallel**
```powershell
# In separate PowerShell windows
python censor_profanity.py video1.mp4 out1.mp4 &
python censor_profanity.py video2.mp4 out2.mp4 &
python censor_profanity.py video3.mp4 out3.mp4 &
```

**Option 4: Optimize Encoding Settings**
Edit `censor_profanity.py`:
```python
# Change preset (faster encoding)
'-preset', 'fast',  # ultrafast, superfast, veryfast, faster, fast, medium, slow

# Or change quality
'-crf', '28',  # higher = smaller file, faster encoding
```

---

## Problem: "File access denied" or "file locked"

### Error Messages
```
PermissionError: [Errno 13] Permission denied
The process cannot access the file because it is being used by another process
```

### Causes
- File still being written
- File in use by another application
- Insufficient permissions
- Windows indexing the file

### Solutions

**Option 1: Wait for File to Complete Writing**
```powershell
# The script automatically waits
# Or manually wait before running:
Start-Sleep -Seconds 5
```

**Option 2: Close Applications Using File**
- Close media players
- Close file explorers with the file open
- Stop antivirus scans on that folder

**Option 3: Run as Administrator**
```powershell
# Right-click PowerShell → "Run as administrator"
# Then run the script
.\convert-profanity-censor.ps1
```

**Option 4: Disable Indexing on Folder**
```powershell
# Right-click folder → Properties → Advanced
# Uncheck "Allow this folder to have its contents indexed"
```

---

## Problem: "No output file created"

### Error Message
```
[-] Output file was not created
```

### Causes
- FFmpeg command failed silently
- Input file format not supported
- Corrupted input file
- Insufficient disk space
- Audio muting filter failed

### Solutions

**Option 1: Check Input File Format**
```powershell
ffprobe -show_format -show_streams input.mp4
```

Look for:
- Video codec (should be recognizable)
- Audio stream present
- Duration and bitrate reasonable

**Option 2: Verify File Integrity**
```powershell
# Play file to test
ffplay input.mp4

# Or check duration
ffprobe -show_entries format=duration -v quiet input.mp4
```

**Option 3: Check Disk Space**
```powershell
Get-Volume C: | Select-Object SizeRemaining
# Should show free space in bytes
# Divide by 1GB to get GB
```

Need at least 2x the input file size free.

**Option 4: Test with Different Encoder**
Edit `censor_profanity.py`, change:
```python
'-c:v', 'libx264',  # Instead of h264_nvenc
```

**Option 5: Enable Verbose Output**
Edit `censor_profanity.py`:
```python
# Change this line:
subprocess.run(cmd, check=True, capture_output=True)

# To this:
subprocess.run(cmd, check=True)  # Shows all output
```

---

## Problem: "Profanity detection not working"

### Symptoms
- Profanity words not detected
- No words muted in output
- Filter generated but no effect

### Causes
- Transcription accuracy too low
- Profanity not in default list
- Filter syntax incorrect
- Audio quality too poor

### Solutions

**Option 1: Verify Transcription**
```powershell
# Run report-only mode to check transcription without producing output
python censor_profanity.py input.mp3 out.mp3 large . --report-only
```

If profanity not in transcription, audio quality may be the issue.

**Option 2: Add Custom Profanity Words**
Edit `censor_profanity.py`:
```python
from better_profanity import profanity
profanity.load_censor_words()

# Add custom words
custom_words = ['word1', 'word2', 'word3']
for word in custom_words:
    profanity.add_profanity(word)
```

**Option 3: Test Profanity Detection**
```powershell
python test-setup.py
```

Check profanity detection section for results.

**Option 4: Improve Audio Quality**
```powershell
# Boost audio before processing
ffmpeg -i input.mp4 -af "volume=1.5" input-boosted.mp4

python censor_profanity.py input-boosted.mp4 output.mp4
```

---

## Problem: "Whisper can't parse audio"

### Error Messages
```
RuntimeError: No audio chunks could be extracted
RuntimeError: Trying to resize sample which is shorter
```

### Causes
- Audio codec not supported
- Very short audio file
- Corrupted audio stream
- Wrong sample rate

### Solutions

**Option 1: Re-encode Audio**
```powershell
# Convert to WAV (universally supported)
ffmpeg -i input.mp4 -q:a 9 -n temp_audio.wav

python censor_profanity.py temp_audio.wav output.mp4
```

**Option 2: Extract and Check Audio**
```powershell
# Extract audio
ffmpeg -i input.mp4 -vn audio.m4a

# Check properties
ffprobe -show_format -show_streams audio.m4a
```

**Option 3: Normalize Audio**
```powershell
ffmpeg -i input.mp4 -af "loudnorm" normalized.mp4

python censor_profanity.py normalized.mp4 output.mp4
```

---

## Problem: "Filter syntax errors"

### Error Messages
```
Filtergraph '...' contains an unescaped ','
Option volume not found
Unrecognized option 'af'
```

### Causes
- FFmpeg version < 4.0
- Filter escaping issues
- Timestamp formatting incorrect

### Solutions

**Option 1: Update FFmpeg**
```powershell
# Check version
ffmpeg -version

# Should be 4.0 or higher
# Download latest from: https://ffmpeg.org/download.html
```

**Option 2: Verify Filter Syntax**
```powershell
# Test filter manually
ffmpeg -i input.mp4 -af "volume=0" output.mp4
```

**Option 3: Simplify Filter**
If complex filter fails, test basic muting:
```powershell
ffmpeg -i input.mp4 -af "volume=0:enable='between(t,1,2)'" output.mp4
```

---

## Problem: "PowerShell execution policy"

### Error Message
```
cannot be loaded because running scripts is disabled on this system
```

### Solution
```powershell
# Temporarily allow
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process

# Then run
.\convert-profanity-censor.ps1

# Or permanently (use with caution)
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

---

## Diagnostic Tools

### Run Full Diagnostics
```powershell
python diagnostics.py
```

Checks everything automatically and suggests fixes.

### Test Installation
```powershell
python test-setup.py
```

Verifies all dependencies are working.

### Check FFmpeg Capabilities
```powershell
# List all encoders
ffmpeg -encoders

# Check for NVENC
ffmpeg -encoders | findstr nvenc

# Test filter
ffmpeg -f lavfi -i testsrc=duration=1:size=320x240:rate=1 -vf "volume=0" -f null -
```

---

## Getting Help

1. **Run Diagnostics First**
   ```powershell
   python diagnostics.py
   ```

2. **Check Relevant Section Above**
   - Find your error message
   - Follow step-by-step solutions

3. **Review Documentation**
   - `README.md` - Full reference
   - `QUICKSTART.md` - Setup help
   - `PROJECT_SUMMARY.md` - Overview

4. **Test Individual Components**
   ```powershell
   python test-setup.py  # Test installation
   ffmpeg -version       # Test FFmpeg
   python -c "from faster_whisper import WhisperModel; print('OK')"  # Test faster-whisper
   ```

5. **Enable Verbose Logging**
   - Edit scripts to show full output
   - Check logs in censor_profanity.log
   - Review ffmpeg error messages

---

## Common Combinations & Solutions

### "I just installed everything and nothing works"
1. Restart PowerShell (important!)
2. Run: `python diagnostics.py`
3. Follow suggestions from diagnostics output

### "Video is slow to process"
1. Check GPU: `ffmpeg -encoders | findstr nvenc`
2. If no NVENC: `h264_qsv`, `h264_videotoolbox`, or `libx264` will be used automatically
3. If transcription is still slow: confirm the automatic Whisper profile in `diagnostics.py` and reduce competing system load

### "Profanity not being detected"
1. Check transcription: Run test-setup.py
2. Verify audio quality: `ffplay input.mp3`
3. Add custom words to better-profanity
4. Confirm that the transcript was generated with the required Whisper `large-v3` model

### "Can't find any of the Python files"
1. Verify you're in correct folder: `Get-Location`
2. List files: `ls`
3. Check file permissions: `Get-Item censor_profanity.py | Get-Acl`

---

**Last Updated**: 2026-07-30
**Version**: 1.0

For additional support, consult README.md or run `python diagnostics.py`
