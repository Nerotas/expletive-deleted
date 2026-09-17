#!/usr/bin/env python3
"""Compatibility entrypoint for the private Electron child process."""

from backend.desktop import DesktopBridge
from backend.desktop.protocol import main, serve
from backend.process_lifetime import contain_process_tree

__all__ = ["DesktopBridge", "main", "serve", "contain_process_tree"]

if __name__ == "__main__":
    raise SystemExit(main())
