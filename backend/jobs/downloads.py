"""Remote YouTube imports, intentionally separate from local Path media jobs."""

from __future__ import annotations

from collections.abc import Callable
import json
import re
import shutil
import subprocess
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Event, RLock
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from backend.runtime import available_encoders, find_ffmpeg, find_ffprobe, select_working_video_encoder
from backend.runtime.environment import get_managed_ffmpeg_paths, get_managed_ytdlp_path
from backend.settings import AppSettings

from .events import JobEvent
from .models import JobError


_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
SUPPORTED_COOKIE_BROWSERS = frozenset({"brave", "chrome", "edge", "firefox"})


class YtdlpAuthenticationRequired(RuntimeError):
    code = "authentication_required"

    def __init__(self, diagnostic: str):
        super().__init__("YouTube requires authentication or verification")
        self.diagnostic = diagnostic


def validate_youtube_url(value: str) -> tuple[str, str]:
    parsed = urlparse(value.strip())
    host = (parsed.hostname or "").casefold()
    if host == "youtu.be":
        video_id = parsed.path.strip("/").split("/")[0]
    elif host in {"youtube.com", "www.youtube.com", "m.youtube.com"} and parsed.path == "/watch":
        query = parse_qs(parsed.query)
        if "list" in query and not query.get("v"):
            raise ValueError("Playlists are not supported; use an individual YouTube video URL")
        video_id = query.get("v", [""])[0]
    else:
        raise ValueError("Only individual YouTube video URLs are supported")
    if not _VIDEO_ID.fullmatch(video_id):
        raise ValueError("Enter an individual YouTube video URL")
    return value.strip(), video_id


@dataclass(frozen=True)
class DownloadRecord:
    id: str
    url: str
    video_id: str
    status: str = "queued"
    title: str | None = None
    cookie_browser: str | None = None
    progress_percent: float | None = None
    error: JobError | None = None

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "source": self.url, "source_type": "youtube", "url": self.url,
                "video_id": self.video_id, "status": self.status, "title": self.title,
                "progress_percent": self.progress_percent, "cookie_browser": self.cookie_browser,
                "error": self.error.to_dict() if self.error else None}


class DownloadManager:
    """One serial network/media lane, independent of transcription work."""
    def __init__(self, settings: AppSettings, on_completed: Callable[[Path], None] | None = None):
        self.settings = settings
        self._on_completed = on_completed
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="youtube-download")
        self._lock = RLock()
        self._records: dict[str, DownloadRecord] = {}
        self._events: dict[str, list[JobEvent]] = {}
        self._cancellations: dict[str, Event] = {}
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self._sequence = 0

    def submit(self, url: str, retry_id: str | None = None, cookie_browser: str | None = None) -> DownloadRecord:
        url, video_id = validate_youtube_url(url)
        if cookie_browser is not None and cookie_browser not in SUPPORTED_COOKIE_BROWSERS:
            raise ValueError("Choose a supported browser session")
        ytdlp = self.settings.runtime.ytdlp_path or get_managed_ytdlp_path()
        if not ytdlp.is_file():
            raise RuntimeError("yt-dlp is not installed. Get it from System Requirements before importing YouTube videos.")
        title = self._resolve_title(ytdlp, url, cookie_browser)
        with self._lock:
            prior = self._records.get(retry_id) if retry_id else None
            if retry_id and (prior is None or prior.url != url):
                raise ValueError("Download retry is unavailable")
            if not retry_id and any(job.url == url and job.status in {"queued", "downloading", "preparing"} for job in self._records.values()):
                raise ValueError("This YouTube video is already downloading")
            job_id = retry_id or uuid4().hex
            record = DownloadRecord(job_id, url, video_id, title=title, cookie_browser=cookie_browser) if prior is None else replace(prior, status="queued", title=title, cookie_browser=cookie_browser, progress_percent=None, error=None)
            self._records[job_id], self._events[job_id], self._cancellations[job_id] = record, [], Event()
            self._emit(job_id, "stage", stage="queued", message="Download queued")
            self._executor.submit(self._run, job_id)
            return record

    def list(self) -> tuple[DownloadRecord, ...]:
        with self._lock: return tuple(self._records.values())

    def events(self, job_id: str) -> tuple[JobEvent, ...]:
        with self._lock: return tuple(self._events[job_id])

    def cancel(self, job_id: str) -> DownloadRecord:
        with self._lock:
            self._cancellations[job_id].set()
            process = self._processes.get(job_id)
            if process and process.poll() is None: process.terminate()
            return self._records[job_id]

    def close(self) -> None: self._executor.shutdown(wait=False, cancel_futures=True)

    def _emit(self, job_id: str, event: str, **values: object) -> None:
        self._sequence += 1
        self._events[job_id].append(JobEvent(event, job_id, sequence=self._sequence, **values))

    def _set(self, job_id: str, status: str, percent: float | None = None, title: str | None = None, error: JobError | None = None, message: str | None = None) -> None:
        current = self._records[job_id]
        self._records[job_id] = replace(current, status=status, progress_percent=percent, title=title or current.title, error=error)
        self._emit(job_id, "error" if error else "completed" if status == "completed" else "stage", stage=status, percent=percent, error=error, message=message)

    def _run(self, job_id: str) -> None:
        staging = self.settings.directories.input.resolve() / ".downloads" / job_id
        try:
            ytdlp = self.settings.runtime.ytdlp_path or get_managed_ytdlp_path()
            if not ytdlp.is_file(): raise RuntimeError("yt-dlp is not installed. Get it from System Requirements before importing YouTube videos.")
            record = self._records[job_id]
            self._set(job_id, "downloading", 0, message="Starting download")
            ffmpeg, ffprobe = self._runtime_media_tools()
            if not ffmpeg or not ffprobe: raise RuntimeError("FFmpeg and FFprobe must be ready before importing YouTube videos")
            staging.mkdir(parents=True, exist_ok=True)
            record, cancellation = self._records[job_id], self._cancellations[job_id]
            command = [str(ytdlp), "--ignore-config"]
            if record.cookie_browser:
                command.extend(["--cookies-from-browser", record.cookie_browser])
            command.extend(["--ffmpeg-location", str(ffmpeg.parent), "--no-playlist", "--newline", "--progress-template", "ED:%(progress._percent_str)s|%(progress.eta)s", "--merge-output-format", "mp4", "-f", "bv*[vcodec^=avc1]+ba[acodec^=mp4a]/b[ext=mp4]/b", "--paths", str(staging), "--output", "source.%(ext)s", record.url])
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
            with self._lock: self._processes[job_id] = process
            output: list[str] = []
            for line in process.stdout or ():
                output.append(line)
                line = line.strip()
                if line.startswith("ED:"):
                    fields = line[3:].split("|")
                    try: percent = float(fields[0].strip().rstrip("%"))
                    except ValueError: percent = None
                    self._set(job_id, "downloading", percent, message="Downloading video")
                    self._emit(job_id, "progress", stage="downloading", percent=percent, eta_seconds=_float(fields[1]) if len(fields) > 1 else None, message="Downloading video")
                if cancellation.is_set(): process.terminate(); raise InterruptedError
            if process.wait() != 0: raise self._download_error("".join(output))
            source = next((item for item in staging.glob("source.*") if item.suffix != ".part"), None)
            if source is None: raise RuntimeError("yt-dlp completed without creating media")
            final = staging / "final.mp4"
            self._set(job_id, "preparing", message="Preparing H.264/AAC MP4")
            self._prepare(job_id, source, final, str(ffmpeg), str(ffprobe), cancellation)
            title = self._records[job_id].title or record.video_id
            destination = self._destination(title, record.video_id)
            if destination.exists(): raise RuntimeError(f"A file named {destination.name} already exists in Ready")
            final.replace(destination)
            self._set(job_id, "completed", 100, message="Added to Ready")
            if self.settings.processing.auto_transcode_youtube_downloads and self._on_completed:
                self._on_completed(destination)
        except InterruptedError: self._set(job_id, "cancelled", message="Download cancelled")
        except Exception as exc:
            authentication_required = isinstance(exc, YtdlpAuthenticationRequired)
            self._set(job_id, "failed", error=JobError(
                "authentication_required" if authentication_required else "download_failed",
                "YouTube needs your browser session" if authentication_required else "YouTube download failed",
                str(exc),
                True,
                exc.diagnostic if authentication_required else traceback.format_exc(),
            ), message="YouTube authentication required" if authentication_required else "YouTube download failed")
        finally:
            with self._lock: self._processes.pop(job_id, None)
            shutil.rmtree(staging, ignore_errors=True)

    def _prepare(self, job_id: str, source: Path, final: Path, ffmpeg: str, ffprobe: str, cancellation: Event) -> None:
        duration_seconds = self._duration(source, ffprobe)
        copy = self._run_ffmpeg(job_id, [ffmpeg, "-y", "-i", str(source), "-map", "0:v:0", "-map", "0:a:0", "-c", "copy", str(final)], cancellation, duration_seconds)
        if copy.returncode == 0:
            try: self._verify(final, ffprobe); return
            except RuntimeError: final.unlink(missing_ok=True)
        encoder = select_working_video_encoder(ffmpeg, available_encoders(ffmpeg))
        convert = self._run_ffmpeg(job_id, [ffmpeg, "-y", "-i", str(source), "-map", "0:v:0", "-map", "0:a:0", "-c:v", encoder, "-c:a", "aac", str(final)], cancellation, duration_seconds)
        if cancellation.is_set(): raise InterruptedError
        if convert.returncode: raise RuntimeError((convert.stderr or convert.stdout or "FFmpeg conversion failed").strip().splitlines()[-1])
        self._verify(final, ffprobe)

    def _run_ffmpeg(self, job_id: str, command: list[str], cancellation: Event, duration_seconds: float | None) -> subprocess.CompletedProcess[str]:
        progress_command = [command[0], "-progress", "pipe:2", "-nostats", *command[1:]]
        process = subprocess.Popen(progress_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        with self._lock:
            self._processes[job_id] = process
        encoded_seconds = 0.0
        output: list[str] = []
        for line in process.stdout or ():
            output.append(line)
            key, separator, value = line.strip().partition("=")
            if separator and key in {"out_time_us", "out_time_ms"}:
                try: encoded_seconds = max(encoded_seconds, int(value) / 1_000_000)
                except ValueError: pass
            elif key == "progress" and duration_seconds and encoded_seconds:
                percent = min(100.0, encoded_seconds / duration_seconds * 100)
                self._set(job_id, "preparing", percent, message="Preparing H.264/AAC MP4")
                self._emit(job_id, "progress", stage="preparing", percent=percent, message="Preparing H.264/AAC MP4")
            if cancellation.is_set():
                process.terminate()
                raise InterruptedError
        process.wait()
        return subprocess.CompletedProcess(progress_command, process.returncode, "".join(output), "")

    @staticmethod
    def _duration(path: Path, ffprobe: str) -> float | None:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True,
            text=True,
        )
        try:
            duration = float(result.stdout.strip())
        except ValueError:
            return None
        return duration if result.returncode == 0 and duration > 0 else None

    @staticmethod
    def _verify(path: Path, ffprobe: str) -> None:
        result = subprocess.run([ffprobe, "-v", "error", "-show_entries", "stream=codec_type,codec_name", "-of", "json", str(path)], capture_output=True, text=True)
        try: codecs = {(entry.get("codec_type"), entry.get("codec_name")) for entry in json.loads(result.stdout).get("streams", [])}
        except json.JSONDecodeError as exc: raise RuntimeError("FFprobe could not read prepared output") from exc
        if not path.is_file() or path.stat().st_size == 0 or ("video", "h264") not in codecs or ("audio", "aac") not in codecs: raise RuntimeError("Prepared output is not a readable H.264 video with AAC audio")

    def _destination(self, title: str, video_id: str) -> Path:
        safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title).strip(" .") or video_id
        return self.settings.directories.input.resolve() / f"{safe[:180]} [{video_id}].mp4"

    @staticmethod
    def _resolve_title(ytdlp: Path, url: str, cookie_browser: str | None = None) -> str:
        """Read structured metadata without downloading media or parsing console output."""
        result = subprocess.run(
            [str(ytdlp), "--ignore-config", *(["--cookies-from-browser", cookie_browser] if cookie_browser else []), "--no-playlist", "--skip-download", "--dump-single-json", url],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip().splitlines()
            raise DownloadManager._download_error(result.stderr or result.stdout)
        try:
            title = json.loads(result.stdout).get("title")
        except json.JSONDecodeError as exc:
            raise RuntimeError("yt-dlp returned invalid video metadata") from exc
        if not isinstance(title, str) or not title.strip():
            raise RuntimeError("yt-dlp did not return a video title")
        return title.strip()

    @staticmethod
    def _download_error(output: str) -> RuntimeError:
        detail = output.strip() or "yt-dlp could not download this video"
        authentication_markers = (
            "sign in to confirm", "authentication", "login required", "cookies-from-browser",
            "confirm your age", "verify that you are not a bot", "verify you're not a bot",
        )
        if any(marker in detail.casefold() for marker in authentication_markers):
            return YtdlpAuthenticationRequired(detail)
        return RuntimeError(detail.splitlines()[-1])

    def _runtime_media_tools(self) -> tuple[Path | None, Path | None]:
        """Use configured tools first, then the verified managed FFmpeg pair."""
        configured_ffmpeg = self.settings.runtime.ffmpeg_path
        configured_ffprobe = self.settings.runtime.ffprobe_path
        if configured_ffmpeg and configured_ffprobe:
            return configured_ffmpeg, configured_ffprobe
        managed_ffmpeg, managed_ffprobe = get_managed_ffmpeg_paths()
        if managed_ffmpeg and managed_ffprobe:
            return Path(managed_ffmpeg), Path(managed_ffprobe)
        return (
            Path(find_ffmpeg()) if find_ffmpeg() else None,
            Path(find_ffprobe()) if find_ffprobe() else None,
        )


def _float(value: str) -> float | None:
    try: return float(value)
    except ValueError: return None