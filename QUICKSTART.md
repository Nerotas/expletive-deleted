# Quick Start

1. Install FFmpeg for your operating system. On Windows use `winget install --id Gyan.FFmpeg.Shared -e` or, when Chocolatey is installed, `choco install ffmpeg -y`.
2. Run `python setup.py --install-system-dependencies` from this repository.
3. Run `.\.venv\Scripts\python.exe diagnostics.py` on Windows, or `.venv/bin/python diagnostics.py` on macOS/Linux.
4. Put media files in `%USERPROFILE%\Documents\Profanity Censor\Ready` or your configured input directory.
5. Run `.\.venv\Scripts\python.exe batch_process.py`. Censorship processing always uses Whisper `large-v3`.

Use `batch_process.py --list` to inspect files before processing. By default, censored media is written to `Finished`, transcripts are written to `Transcripts`, and the original remains in `Ready`. Use `--archive-original` to move originals to `Processed` only after verified success.

Inspect or change directories before processing:

```powershell
.\.venv\Scripts\python.exe manage_settings.py show
.\.venv\Scripts\python.exe manage_settings.py set-directories --input 'D:\Media\Ready' --create
```

Run the backend regression suite with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```
