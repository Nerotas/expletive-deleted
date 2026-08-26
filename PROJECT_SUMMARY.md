# Profanity Censoring Workflow - Project Summary

## 📋 What Was Created

A complete automated workflow to detect and censor profanity in audio/video files using Whisper AI and FFmpeg.

### Core Components

#### 1. **censor_profanity.py** - Main Processing Engine
- Transcribes audio using faster-whisper (CTranslate2 backend)
- Detects profanity using better-profanity library
- Generates FFmpeg muting filters for profanity timestamps
- Applies audio muting to video/audio output
- Supports hardware-accelerated video encoding (NVENC/QSV/VideoToolbox)

**Usage:**
```powershell
python censor_profanity.py input.mp4 output.mp4 large [transcripts_dir]
```

#### 2. **convert-profanity-censor.ps1** - Watch Folder Automation
- Monitors `ready/` folder for new files
- Automatically processes detected media files
- Moves processed files to `processed/` folder
- Outputs censored files to `transcoded/` folder
- Works with `.mp4`, `.mkv`, `.avi`, `.mov`, `.wmv`, `.flv`, `.webm`, `.mp3`, `.m4a`, `.wav`

**Usage:**
```powershell
.\convert-profanity-censor.ps1
```

#### 3. **setup.py** - Dependency Installation
- Checks system for FFmpeg and Python
- Installs required Python packages:
  - faster-whisper
  - better-profanity
  - numpy

**Usage:**
```powershell
python setup.py
```

#### 4. **test-setup.py** - Installation Verification
- Tests all dependencies
- Verifies library functionality
- Safe to run multiple times

**Usage:**
```powershell
python test-setup.py
```

#### 5. **batch_process.py** - Batch Processing
- Process multiple files at once
- Supports parallel processing
- List files without processing

**Usage:**
```powershell
python batch_process.py "videos/*.mp4" -o output_folder -m base -w 2
```

#### 6. **diagnostics.py** - System Diagnostics
- Checks system requirements
- Verifies all installations
- Tests file access and disk space
- Suggests fixes for issues

**Usage:**
```powershell
python diagnostics.py
```

### Documentation Files

#### **README.md** - Complete Reference
- Full feature overview
- System requirements
- Installation instructions for Windows
- Usage examples (batch and single file)
- Configuration options
- Performance tips and optimization
- Troubleshooting guide
- Advanced usage examples

#### **QUICKSTART.md** - Fast Setup Guide
- 5-minute FFmpeg setup
- Python dependency installation
- Verification steps
- First test with sample file
- Common issues and fixes

#### **config.ini** - Configuration Template
- Customizable paths
- Whisper model selection
- Processing options (encoders, codecs)
- Profanity detection settings
- Logging configuration
- Advanced settings

## 🔄 Workflow Overview

```
ready/ folder (input)
    ↓
[Extract audio from video]
    ↓
[Whisper transcription] → Get word timestamps
    ↓
[Detect profanity] → Identify bad words
    ↓
[Generate FFmpeg filter] → Mute at timestamps
    ↓
[Apply with FFmpeg] → Output video
    ↓
transcoded/ folder (output)
processed/ folder (archive)
```

## 🚀 Quick Start

### 1. One-Time Setup (10 minutes)
```powershell
# Install FFmpeg (manual - see QUICKSTART.md)
# Then:
python setup.py
python test-setup.py
```

### 2. Drop Files & Run
```powershell
# Copy audio/video to ready/ folder
# Start the watch script
.\convert-profanity-censor.ps1
```

### 3. Collect Output
- Censored files in `transcoded/`
- Original files archived in `processed/`

## 📊 Key Features

✅ **Accurate Detection**
- Word-level profanity detection (single words)
- Uses industry-standard better-profanity library
- Customizable word lists

✅ **High Performance**
- faster-whisper runs 4–8× faster than openai-whisper on GPU
- Hardware-accelerated video encoding (NVENC/QSV/VideoToolbox)
- Automatic fallback to software encoding

✅ **Flexible Transcription**
- Multiple Whisper model sizes (tiny → large)
- Speed vs. accuracy trade-off
- Auto-detection of word timestamps

✅ **Automation**
- Watch folder functionality
- Batch processing
- File locking detection
- Automatic archival

✅ **User Friendly**
- PowerShell scripts for Windows
- Detailed logging and progress
- Diagnostic tools
- Comprehensive documentation

## 🛠️ Technology Stack

| Component | Purpose | Link |
|-----------|---------|------|
| faster-whisper | Speech-to-text transcription | https://github.com/SYSTRAN/faster-whisper |
| better-profanity | Profanity detection | https://github.com/better-profanity/better-profanity |
| FFmpeg | Audio/video encoding | https://ffmpeg.org |
| Python 3.8+ | Runtime | https://python.org |
| Windows 10/11 | Operating system | - |

## 📝 File Structure

```
C:\Users\Nerot\Downloads\temp\
├── censor_profanity.py              ← Main processing engine
├── convert-profanity-censor.ps1     ← Watch folder script
├── batch_process.py                 ← Batch processing
├── setup.py                         ← Install dependencies
├── test-setup.py                    ← Verify installation
├── diagnostics.py                   ← System diagnostics
├── config.ini                       ← Configuration template
├── README.md                        ← Full documentation
├── QUICKSTART.md                    ← Quick setup guide
├── PROJECT_SUMMARY.md               ← This file
│
├── ready/                           ← Input folder (watch)
│   └── ProfanityTest.mp3           ← Test file
│
├── transcoded/                      ← Output (censored files)
│   └── [processed files]
│
└── processed/                       ← Archive (original files)
    └── [archived files]
```

## 🎯 Use Cases

### 1. **Broadcast & Streaming**
- Auto-censor profanity in live streams
- Maintain broadcast standards
- Reduce manual moderation

### 2. **Content Creation**
- Clean up podcast audio
- Remove profanity from uploads
- Meet platform guidelines (YouTube, TikTok, etc.)

### 3. **Batch Processing**
- Process entire video libraries
- Archive and organize
- Maintain consistency

### 4. **Training & Testing**
- Generate clean training data
- Test profanity filter effectiveness
- Quality assurance

## ⚡ Performance Expectations

### Hardware Requirements
- **Minimum**: 8GB RAM, CPU with 4+ cores
- **Recommended**: 16GB RAM and a modern CPU with 4+ cores; an optional supported GPU can also accelerate Whisper and FFmpeg encoding
- **Disk**: Minimum 5GB free for temp + output

### Processing Times (Approx.)
| Duration | Model | CPU time |
|----------|-------|----------|
| 1 minute | large | varies by hardware |
| 10 minutes | large | varies by hardware |
| 1 hour | large | varies by hardware |

*Times vary based on system specs and audio complexity*

## 🔧 Configuration Examples

### Required Censorship Model
The workflow enforces Whisper `large-v3` to preserve word-level timestamp accuracy for audio muting.

## 🆘 Support

1. **Quick Help**: See `QUICKSTART.md`
2. **Full Guide**: See `README.md`
3. **Diagnose Issues**: Run `python diagnostics.py`
4. **Test Setup**: Run `python test-setup.py`

## 📦 Requirements Summary

### System
- Windows 10/11
- 8GB+ RAM
- 5GB+ free disk space
- Optional supported GPU for adaptive Whisper and FFmpeg video encoding acceleration

### Software
- Python 3.9+
- FFmpeg 4.0+
- PowerShell 5.0+

### Python Packages
- faster-whisper
- better-profanity
- numpy

## 🎓 Learning Resources

- **faster-whisper Docs**: https://github.com/SYSTRAN/faster-whisper
- **FFmpeg Filters**: https://ffmpeg.org/ffmpeg-filters.html
- **better-profanity**: https://github.com/better-profanity/better-profanity

## 📋 Checklist for First Use

- [ ] Install FFmpeg (see QUICKSTART.md)
- [ ] Run `python setup.py` to install dependencies
- [ ] Run `python test-setup.py` to verify
- [ ] Copy test file to `ready/` folder
- [ ] Run `.\convert-profanity-censor.ps1`
- [ ] Wait for processing to complete
- [ ] Check output in `transcoded/` folder
- [ ] Review the censored file

## 🎯 Next Steps

1. **Immediate**: Follow QUICKSTART.md for 10-minute setup
2. **Short Term**: Test with ProfanityTest.mp3 sample
3. **Medium Term**: Configure for your specific use case (edit config.ini)
4. **Long Term**: Run as automated service in background

## 📞 Troubleshooting Flowchart

```
Issue?
├─ "FFmpeg not found" → Add to PATH, restart
├─ "Module not found" → Run: pip install [package]
├─ "Out of memory" → Close applications, increase virtual memory, or split media
├─ "No output" → Check input format with ffprobe
├─ "Slow processing" → Enable the automatically selected supported GPU profile or reduce competing load
└─ "File locked" → Ensure copy is complete before processing
```

## 🚀 Production Deployment

When ready for production:

1. **Automate with Task Scheduler**
   ```powershell
   # Create scheduled task to run convert-profanity-censor.ps1 on startup
   ```

2. **Monitor with Logging**
   - Enable detailed logs in config.ini
   - Review censor_profanity.log regularly

3. **Optimize Performance**
   - Test with your typical files
   - Adjust model size for speed/accuracy balance
   - Enable hardware acceleration if available

4. **Backup & Archive**
   - Keep original files in processed/ folder
   - Periodically backup transcoded/ folder

---

**Version**: 1.0
**Created**: 2026-07-30
**Status**: Production Ready ✅

For questions or issues, refer to README.md or run `python diagnostics.py`
