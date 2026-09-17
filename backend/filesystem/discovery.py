"""Walk approved directories without traversing escaped links or staged output."""

from pathlib import Path

from .paths import PathSafetyError, RootBinding


def files_within(root: RootBinding, *, recursive=True):
    visited = set()

    def walk(directory: Path):
        resolved = root.target(directory)
        if resolved in visited:
            return
        visited.add(resolved)
        with root.lease(directory / '.scan'):
            for child in directory.iterdir():
                if child.name.startswith('.') or child.is_symlink():
                    continue
                try:
                    root.target(child)
                except (PathSafetyError, OSError, RuntimeError):
                    continue
                if child.is_dir():
                    if recursive:
                        yield from walk(child)
                elif child.is_file():
                    yield child

    yield from walk(root.configured)
