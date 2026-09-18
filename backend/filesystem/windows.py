"""Small Windows handle adapter; no shell commands or third-party dependencies."""

from __future__ import annotations

import ctypes
import os
import msvcrt
import time
from ctypes import wintypes
from pathlib import Path

_kernel = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                              ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
_kernel.CreateFileW.restype = wintypes.HANDLE
_kernel.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel.CloseHandle.restype = wintypes.BOOL
_kernel.SetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
_kernel.SetFileInformationByHandle.restype = wintypes.BOOL
_kernel.GetCurrentProcess.restype = wintypes.HANDLE
_kernel.DuplicateHandle.argtypes = [wintypes.HANDLE, wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.HANDLE), wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel.DuplicateHandle.restype = wintypes.BOOL


class Handle:
    """Pin an entry against replacement, deletion, and reparse-point edits."""

    def __init__(self, path: Path, *, directory: bool = False, mutable: bool = False, writable: bool = False, create: bool = False, temporary: bool = False):
        self.path = path
        # Share reads only: denying DELETE pins the name; denying WRITE pins junction data.
        access = 0x80000000 | (0x10000 if mutable else 0)  # GENERIC_READ, DELETE
        self.value = _kernel.CreateFileW(str(path), access, 3 if writable else 1, None, 1 if create else 3,
                                       0x00200000 | (0x02000000 if directory else 0) | (0x04000102 if temporary else 0), None)
        if self.value == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.value is not None:
            _kernel.CloseHandle(self.value)
            self.value = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def rename(self, destination: Path):
        """Rename this exact open file, refusing any competing destination."""
        name = destination.name
        class RenameInfo(ctypes.Structure):
            _fields_ = [("replace", wintypes.BOOLEAN), ("root", wintypes.HANDLE),
                        ("length", wintypes.DWORD), ("name", wintypes.WCHAR * (len(name.encode('utf-16-le')) // 2 + 1))]
        with Handle(destination.parent, directory=True, writable=True) as parent:
            value = RenameInfo(False, parent.value, len(name.encode("utf-16-le")), name)
            native = ctypes.WinDLL('ntdll')
            native.NtSetInformationFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, wintypes.ULONG, ctypes.c_int]
            native.NtSetInformationFile.restype = wintypes.LONG
            native.RtlNtStatusToDosError.argtypes = [wintypes.LONG]
            native.RtlNtStatusToDosError.restype = wintypes.ULONG
            io_status = (ctypes.c_void_p * 2)()
            # Another publisher briefly denies child renames while pinning this
            # directory. Retry only sharing conflicts with the same pinned handles.
            for attempt in range(21):
                status = native.NtSetInformationFile(self.value, ctypes.byref(io_status), ctypes.byref(value), ctypes.sizeof(value), 10)
                if status >= 0:
                    break
                error = native.RtlNtStatusToDosError(status)
                if error != 32 or attempt == 20:
                    raise ctypes.WinError(error)
                time.sleep(0.025)
        self.path = destination

    def delete(self):
        """Mark the pinned entry for deletion when its final handle closes."""
        value = wintypes.BOOLEAN(True)
        for attempt in range(21):
            if _kernel.SetFileInformationByHandle(self.value, 4, ctypes.byref(value), ctypes.sizeof(value)):
                return
            error = ctypes.get_last_error()
            if error != 32 or attempt == 20:
                raise ctypes.WinError(error)
            time.sleep(0.025)

    def reader(self):
        """Read a DELETE-capable source without reopening it with conflicting share flags."""
        duplicate = wintypes.HANDLE()
        process = _kernel.GetCurrentProcess()
        if not _kernel.DuplicateHandle(process, self.value, process, ctypes.byref(duplicate), 0, False, 2):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            descriptor = msvcrt.open_osfhandle(duplicate.value, os.O_RDONLY | os.O_BINARY)
        except BaseException:
            _kernel.CloseHandle(duplicate)
            raise
        return os.fdopen(descriptor, 'rb')
