"""Containment and directory leases shared by every media write path."""

from __future__ import annotations

import os
import re
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


class PathSafetyError(ValueError):
    code = "unsafe_path"


def validate_path(path: Path) -> Path:
    path = path.expanduser()
    if not path.is_absolute() or ".." in path.parts:
        raise PathSafetyError(f"Choose an absolute path without traversal: {path}")
    if os.name == "nt":
        if str(path).startswith(("\\\\", "\\?\\", "\\.\\")):
            raise PathSafetyError("Device and network paths are not supported for protected media operations")
        for part in path.parts[1:]:
            if (part.endswith((".", " ")) or re.search(r'[<>:"|?*\x00-\x1f]', part)
                    or re.match(r"^(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\.|$)", part, re.I)):
                raise PathSafetyError(f"Unsupported Windows path component: {part}")
    return path


def identity(path: Path) -> tuple[int, int]:
    value = path.stat()
    return value.st_dev, value.st_ino


def version(path: Path):
    value = path.stat()
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


@contextmanager
def pinned_directory(path: Path, *, create: bool = False, boundary=None, mutations=False, read_guard=None):
    """Pin both lexical junctions and their resolved targets before using a path."""
    path = validate_path(path)
    with ExitStack() as stack:
        if os.name == "nt":
            from .windows import Handle
            pinned = set()
            handles = {}

            def pin(current: Path):
                if current in pinned:
                    return
                if current.parent != current:
                    pin(current.parent)
                try:
                    handle = Handle(current, directory=True)
                except FileNotFoundError:
                    if not create:
                        raise
                    current.mkdir()
                    handle = Handle(current, directory=True)
                stack.enter_context(handle)
                handles[current] = handle
                pinned.add(current)
                # The lexical reparse entry is pinned before resolving it.
                resolved = current.resolve(strict=True)
                if boundary and (_inside(current, boundary.configured) or _inside(current, boundary.resolved)):
                    boundary.target(current)
                if resolved != current:
                    pin(resolved)
                if not current.is_dir():
                    raise PathSafetyError(f"Not a directory: {current}")

            pin(path)
            # A pinned child prevents each ancestor from becoming an empty junction.
            # Keep the leaf nonempty too, then permit normal child renames without
            # permitting directory deletion. Junction handles retain deny-WRITE.
            if mutations:
                if read_guard is not None:
                    # A pinned source already keeps the chain nonempty; importing from
                    # a read-only source directory must not require a new sentinel there.
                    stack.enter_context(Handle(read_guard))
                else:
                    sentinel = path / f'.ed-lease-{uuid4().hex}.lock'
                    stack.enter_context(Handle(sentinel, create=True, mutable=True, temporary=True))
                for current, handle in handles.items():
                    if not getattr(current.lstat(), 'st_file_attributes', 0) & 0x400:
                        stack.enter_context(Handle(current, directory=True, writable=True))
                        handle.close()
            yield path.resolve(strict=True)
        else:
            # Descriptor-relative opens never follow an unexamined child link.
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            descriptor = os.open(path.anchor, flags)
            stack.callback(os.close, descriptor)
            for component in path.parts[1:]:
                try:
                    child = os.open(component, flags, dir_fd=descriptor)
                except FileNotFoundError:
                    if not create:
                        raise
                    os.mkdir(component, dir_fd=descriptor)
                    child = os.open(component, flags, dir_fd=descriptor)
                stack.callback(os.close, child)
                descriptor = child
            yield path


@dataclass(frozen=True)
class RootBinding:
    configured: Path
    resolved: Path
    device: int
    inode: int

    @classmethod
    def capture(cls, path: Path) -> RootBinding:
        with pinned_directory(path, create=True) as resolved:
            return cls(path, resolved, *identity(resolved))

    def check(self):
        if self.configured.resolve(strict=True) != self.resolved or identity(self.resolved) != (self.device, self.inode):
            raise PathSafetyError(f"The selected folder changed: {self.configured}. Select its intended target folder again in Settings.")

    def target(self, path: Path) -> Path:
        validate_path(path)
        self.check()
        if not (_inside(path, self.configured) or _inside(path, self.resolved)):
            raise PathSafetyError(f"Path is outside the configured folder: {path}")
        resolved = path.resolve()
        if not _inside(resolved, self.resolved):
            raise PathSafetyError(f"A link escapes the configured folder: {path}")
        return resolved

    @contextmanager
    def lease(self, path: Path, *, create_parent: bool = False, mutations=True):
        """Hold the root and destination chain until the caller finishes its operation."""
        if os.name != "nt":
            raise PathSafetyError("Protected media mutations currently require Windows handle leases; this platform cannot pin directory renames")
        read_guard = None if mutations else path
        self.target(path)
        with pinned_directory(self.configured, boundary=self, mutations=True, read_guard=read_guard):
            self.target(path)
            # Validate ancestors before creating them; recheck while the entire chain is pinned.
            with pinned_directory(path.parent, create=create_parent, boundary=self, mutations=True, read_guard=read_guard):
                resolved = self.target(path)
                yield resolved


def reject_alias(source: Path, destination: Path):
    if source.resolve() == destination.resolve() or (destination.exists() and os.path.samefile(source, destination)):
        raise PathSafetyError("Source and destination refer to the same file; the original must remain unchanged")
