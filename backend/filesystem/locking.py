"""Reentrant thread/process ownership for cooperating local stores.

Order: service lifecycle, settings, policy, then destination locks. Never acquire
settings inside a policy transaction or hold persistence locks during processing.
"""

from __future__ import annotations

import errno
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class StoreBusyError(RuntimeError):
    code = "store_busy"


class _Ownership:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.depth = 0


_registry_guard = threading.Lock()
_registry: dict[str, _Ownership] = {}


@contextmanager
def store_lock(path: Path, timeout: float = 5.0) -> Iterator[None]:
    """Lock a permanent file; the OS releases ownership when a process dies."""
    path = path.expanduser().resolve()
    key = os.path.normcase(str(path))
    with _registry_guard:
        ownership = _registry.setdefault(key, _Ownership())
    deadline = time.monotonic() + timeout
    message = "The dictionary is busy in another operation. Wait a moment and retry."
    if not ownership.lock.acquire(timeout=max(0, timeout)):
        raise StoreBusyError(message)
    try:
        if ownership.depth:
            ownership.depth += 1
            try:
                yield
            finally:
                ownership.depth -= 1
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+b") as handle:
            if os.fstat(handle.fileno()).st_size == 0:
                handle.write(b"\0")
                handle.flush()
            while True:
                try:
                    if os.name == "nt":
                        import msvcrt
                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                        raise
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise StoreBusyError(message) from exc
                    time.sleep(min(0.025, remaining))
            ownership.depth = 1
            try:
                yield
            finally:
                ownership.depth = 0
                if os.name == "nt":
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        ownership.lock.release()
