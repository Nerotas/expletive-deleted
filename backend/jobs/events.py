"""Structured events emitted while backend jobs run."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .models import JobError, JobStatus


EventType = Literal["stage", "progress", "detection", "error", "completed"]


@dataclass(frozen=True)
class JobEvent:
    event: EventType
    job_id: str
    sequence: int = 0
    stage: JobStatus | None = None
    percent: float | None = None
    eta_seconds: float | None = None
    fps: float | None = None
    message: str | None = None
    error: JobError | None = None
    word: str | None = None
    start: float | None = None
    end: float | None = None

    def __post_init__(self) -> None:
        if not self.job_id.strip():
            raise ValueError("Event job id must not be empty")
        if self.percent is not None and not 0 <= self.percent <= 100:
            raise ValueError("Event progress must be from 0 through 100")
        if self.eta_seconds is not None and self.eta_seconds < 0:
            raise ValueError("Event ETA must not be negative")
        if self.fps is not None and self.fps < 0:
            raise ValueError("Event FPS must not be negative")
        if self.event == "error" and self.error is None:
            raise ValueError("Error events require an error")
        if self.event != "error" and self.error is not None:
            raise ValueError("Only error events may contain an error")
        if self.event == "detection" and not self.word:
            raise ValueError("Detection events require a word")

    def to_dict(self) -> dict[str, object]:
        return {
            "event": self.event,
            "job_id": self.job_id,
            "sequence": self.sequence,
            "stage": self.stage,
            "percent": self.percent,
            "eta_seconds": self.eta_seconds,
            "fps": self.fps,
            "message": self.message,
            "error": self.error.to_dict() if self.error else None,
            "word": self.word,
            "start": self.start,
            "end": self.end,
        }