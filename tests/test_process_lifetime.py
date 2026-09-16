"""Native Windows regression for bridge-owned children and grandchildren."""

import ctypes
import json
import os
import queue
import subprocess
import sys
import unittest
from ctypes import wintypes
from pathlib import Path
from threading import Thread


@unittest.skipUnless(os.name == "nt", "Windows Job Objects")
class ProcessLifetimeTests(unittest.TestCase):
    def test_normal_and_forced_bridge_exit_terminate_descendants(self):
        child_code = (
            "import json, os, subprocess, sys, time; "
            "grandchild = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
            "print(json.dumps([os.getpid(), grandchild.pid]), flush=True); time.sleep(60)"
        )
        parent_code = (
            "import subprocess, sys; from backend.process_lifetime import contain_process_tree; "
            "contain_process_tree(); "
            f"child = subprocess.Popen([sys.executable, '-c', {child_code!r}], stdout=subprocess.PIPE, text=True); "
            "print(child.stdout.readline(), end='', flush=True); sys.stdin.read()"
        )
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        for forced in (False, True):
            with self.subTest(forced=forced):
                parent = subprocess.Popen(
                    [sys.executable, "-c", parent_code], cwd=Path(__file__).resolve().parents[1],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                handles = []
                try:
                    lines = queue.Queue()
                    Thread(target=lambda: lines.put(parent.stdout.readline()), daemon=True).start()
                    pids = json.loads(lines.get(timeout=15))
                    for pid in pids:
                        handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
                        self.assertTrue(handle)
                        handles.append(handle)
                    if forced:
                        parent.kill()
                    parent.communicate(input="", timeout=10)
                    for handle in handles:
                        self.assertEqual(kernel.WaitForSingleObject(handle, 5000), 0)
                finally:
                    if parent.poll() is None:
                        parent.kill()
                    parent.communicate(timeout=10)
                    for handle in handles:
                        kernel.CloseHandle(handle)
