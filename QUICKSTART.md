# Quick Start

1. Install FFmpeg for your operating system. On Windows use `winget install --id Gyan.FFmpeg.Shared -e` or, when Chocolatey is installed, `choco install ffmpeg -y`.
2. Run `python setup.py --install-system-dependencies` from this repository.
3. Run `.\.venv\Scripts\python.exe diagnostics.py` on Windows, or `.venv/bin/python diagnostics.py` on macOS/Linux.
4. Put media files in `ready/`.
5. Run `.\.venv\Scripts\python.exe batch_process.py`. Censorship processing always uses Whisper `large-v3`.

Use `batch_process.py --list` to inspect files before processing. Censored media is written to `transcoded/`; completed source files are moved to `processed/`; reusable Whisper transcripts are stored in `transcripts/`.