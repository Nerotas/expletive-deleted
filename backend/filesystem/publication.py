"""Verified staging and collision-refusing publication shared by media entrypoints."""

from __future__ import annotations

import os
from contextlib import ExitStack
from pathlib import Path
from threading import Event
from uuid import uuid4

from .paths import PathSafetyError, RootBinding, identity, version, reject_alias
from .operations import locked_file, remove_file, move_file

_UNSET = object()


class PublicationError(RuntimeError):
    def __init__(self, message, code='publication_failed'):
        self.code = code
        super().__init__(message)


class Publication:
    """Own one staging file; cleanup can never delete another writer's result."""

    def __init__(self, root: RootBinding, destination: Path, *, source: Path | None = None,
                 overwrite=False, cancellation: Event | None = None, expected_version=_UNSET):
        self.root, self.destination, self.source = root, destination, source
        self.overwrite = overwrite
        self.cancellation = cancellation or Event()
        self._stack = ExitStack()
        self.stage = None
        self.published = False
        root.target(destination)
        self.expected_version = (version(destination) if destination.exists() else None) if expected_version is _UNSET else expected_version
        self.expected = self.expected_version[:2] if self.expected_version else None

    def check_cancelled(self):
        if self.cancellation.is_set():
            raise InterruptedError('Operation cancelled before publication')

    def __enter__(self):
        try:
            self.destination = self._stack.enter_context(self.root.lease(self.destination, create_parent=True))
            if self.source:
                reject_alias(self.source, self.destination)
            if self.expected is not None and not self.overwrite:
                raise PublicationError(f'Destination already exists: {self.destination}', 'destination_exists')
            self.check_cancelled()
            self.stage = self.destination.with_name(f'.{self.destination.stem}.{uuid4().hex}.partial{self.destination.suffix}')
            from .windows import Handle
            self._keeper = self._stack.enter_context(Handle(self.stage, create=True, writable=True))
            self._stage_identity = identity(self.stage)
            return self
        except BaseException:
            self._stack.close()
            raise

    def publish(self, verify):
        self.check_cancelled()
        if not self.stage.is_file() or self.stage.stat().st_size == 0:
            raise PublicationError('Processing produced an empty or missing output')
        verify(self.stage)
        self.check_cancelled()
        with self.stage.open('r+b') as stream:
            stream.flush()
            os.fsync(stream.fileno())
        self._keeper.close()
        with locked_file(self.root, self.stage, mutable=True, expected=self._stage_identity) as staged:
            self.root.target(self.destination)
            self.check_cancelled()
            if self.expected is None:
                try:
                    staged.rename(self.destination)
                except FileExistsError as exc:
                    raise PublicationError(f'Destination appeared during processing: {self.destination}', 'destination_exists') from exc
            else:
                self._replace(staged)
            self.published = True
        return self.destination

    def _replace(self, staged):
        """Keep the old object pinned and recoverable; never overwrite a racing target."""
        with locked_file(self.root, self.destination, mutable=True, expected=self.expected) as previous:
            if version(self.destination) != self.expected_version:
                raise PathSafetyError(f'Output changed since replacement was authorized: {self.destination}')
            backup = self.destination.with_name(f'.{self.destination.name}.{uuid4().hex}.recovery')
            previous.rename(backup)
            try:
                staged.rename(self.destination)
            except BaseException as exc:
                try:
                    previous.rename(self.destination)
                except OSError:
                    raise PublicationError(f'Publication conflicted; previous output retained at {backup}', 'recovery_required') from exc
                raise
            # Only this exact old object is retired after the new file is in place.
            self.published = True
            try:
                previous.delete()
            except OSError as exc:
                raise PublicationError(f'Output saved; previous output retained at {backup}', 'recovery_required') from exc

    def __exit__(self, *_):
        try:
            if self.stage is not None:
                self._keeper.close()
                if not self.published:
                    try:
                        remove_file(self.root, self.stage, expected=self._stage_identity)
                    except FileNotFoundError:
                        pass
        finally:
            self._stack.close()


def copy_verified(source: Path, publication: Publication, progress=None, *, expected_version=None):
    """Copy under a source lease and verify byte count and source identity."""
    source_root = RootBinding.capture(source.parent)
    with locked_file(source_root, source):
        if expected_version is not None and version(source) != expected_version:
            raise PathSafetyError(f'Source changed while queued: {source}')
        before = source.stat()
        copied = 0
        with source.open('rb') as incoming, publication.stage.open('wb') as outgoing:
            while True:
                publication.check_cancelled()
                chunk = incoming.read(1024 * 1024)
                if not chunk:
                    break
                outgoing.write(chunk)
                copied += len(chunk)
                if progress:
                    progress(copied, before.st_size)
        after = source.stat()
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise PathSafetyError(f'Source changed while copying: {source}')
        if copied != before.st_size or publication.stage.stat().st_size != copied:
            raise PublicationError('Copy did not preserve the complete source')
        publication.publish(lambda _: None)


def move_verified(source_root: RootBinding, source: Path, destination_root: RootBinding, destination: Path, *, expected_version=None):
    """Copy/verify first, then remove exactly the pinned source, including across volumes."""
    if source.stat().st_dev == destination_root.device:
        return move_file(source_root, source, destination_root, destination, expected_version=expected_version)
    with locked_file(source_root, source, mutable=True) as original:
        if expected_version is not None and version(source) != expected_version:
            raise PathSafetyError(f'Source changed before archiving: {source}')
        with Publication(destination_root, destination, source=source) as publication:
            size = source.stat().st_size
            with original.reader() as incoming, publication.stage.open('wb') as outgoing:
                import shutil
                shutil.copyfileobj(incoming, outgoing, 1024 * 1024)
            if publication.stage.stat().st_size != size:
                raise PublicationError('Archive copy is incomplete; source retained')
            publication.publish(lambda _: None)
            original.delete()
    return destination
