"""Identity-bound file reads and removals under a configured directory lease."""

import stat
from contextlib import contextmanager
from pathlib import Path

from .paths import PathSafetyError, RootBinding, identity, version, reject_alias


@contextmanager
def locked_file(root: RootBinding, path: Path, *, mutable=False, expected=None):
    with root.lease(path, mutations=mutable) as resolved:
        # A selected file link is not equivalent to selecting the original file itself.
        if path.is_symlink() or not stat.S_ISREG(path.lstat().st_mode):
            raise PathSafetyError(f"Expected an ordinary file: {path}")
        from .windows import Handle
        with Handle(resolved, mutable=mutable) as handle:
            if expected is not None and identity(resolved) != expected:
                raise PathSafetyError(f"File changed while waiting: {path}")
            yield handle


def remove_file(root: RootBinding, path: Path, *, expected=None):
    with locked_file(root, path, mutable=True, expected=expected) as handle:
        handle.delete()


def move_file(source_root: RootBinding, source: Path, destination_root: RootBinding, destination: Path, *, expected_version=None):
    """Move one pinned source on the same volume; an existing destination always wins."""
    with locked_file(source_root, source, mutable=True) as original:
        if expected_version is not None and version(source) != expected_version:
            raise PathSafetyError(f'Source changed before archiving: {source}')
        with destination_root.lease(destination, create_parent=True) as target:
            reject_alias(source, target)
            original.rename(target)
    return destination


def remove_empty_parents(root: RootBinding, directory: Path):
    from .windows import Handle
    while directory not in (root.configured, root.resolved):
        try:
            with root.lease(directory) as resolved:
                with Handle(resolved, directory=True, mutable=True) as handle:
                    if getattr(resolved.lstat(), 'st_file_attributes', 0) & 0x400 or any(resolved.iterdir()):
                        return
                    handle.delete()
        except (OSError, PathSafetyError):
            return
        directory = directory.parent


def remove_tree(root: RootBinding, directory: Path):
    """Clean generated files without following junctions or deleting a replacement tree."""
    with root.lease(directory / '.cleanup'):
        for child in directory.iterdir():
            if child.name.startswith('.ed-lease-'):
                continue  # These delete-on-close sentinels belong to active directory leases.
            info = child.lstat()
            if child.is_symlink() or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise PathSafetyError(f"Unexpected link in staging: {child}")
            if child.is_dir():
                remove_tree(root, child)
            else:
                remove_file(root, child, expected=identity(child))
    # Pin its parent and remove the directory by its own handle, not by a stale path.
    with root.lease(directory):
        from .windows import Handle
        with Handle(directory, directory=True, mutable=True) as handle:
            handle.delete()
