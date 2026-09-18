"""Mandatory junction and process-race gates on the Windows release target."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from backend.filesystem.paths import PathSafetyError, RootBinding


@unittest.skipUnless(os.name == 'nt', 'Native Windows gate')
class WindowsDestinationGuardTests(unittest.TestCase):
    def junction(self, link, target):
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
        self.addCleanup(lambda: os.rmdir(link) if link.exists() else None)

    def test_approved_root_and_internal_junction_work_but_escape_does_not(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            actual = base / 'actual café 家庭'
            actual.mkdir()
            configured = base / 'configured'
            self.junction(configured, actual)
            root = RootBinding.capture(configured)
            (actual / 'inside').mkdir()
            self.junction(actual / 'link', actual / 'inside')
            outside = base / 'outside'
            outside.mkdir()
            self.junction(actual / 'escape', outside)
            try:
                with root.lease(configured / 'link' / 'new' / 'file.txt', create_parent=True) as destination:
                    destination.write_text('safe')
                self.assertEqual((actual / 'inside' / 'new' / 'file.txt').read_text(), 'safe')
                with self.assertRaises(PathSafetyError):
                    with root.lease(configured / 'escape' / 'new' / 'file.txt', create_parent=True):
                        self.fail('Escaping junction acquired a lease')
                self.assertEqual(list(outside.iterdir()), [])
            finally:
                # Remove junction entries only, never recurse into their targets.
                for link in [actual / 'escape', actual / 'link', configured]:
                    os.rmdir(link)

    def test_other_process_cannot_swap_parent_during_lease(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = RootBinding.capture(Path(temporary) / 'root')
            parent = root.configured / 'parent'
            parent.mkdir()
            with root.lease(parent / 'file.txt') as destination:
                attempt = subprocess.run([sys.executable, '-c',
                    'import os,sys; os.rename(sys.argv[1],sys.argv[2])', str(parent), str(parent.with_name('moved'))],
                    capture_output=True, timeout=10)
                self.assertNotEqual(attempt.returncode, 0)
                destination.write_text('safe')
            parent.rename(parent.with_name('moved'))  # Handles are released on success.

    def test_root_junction_retargeting_is_not_silently_accepted(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            for name in ['first', 'second']:
                (base / name).mkdir()
            link = base / 'root'
            self.junction(link, base / 'first')
            root = RootBinding.capture(link)
            os.rmdir(link)
            self.junction(link, base / 'second')
            try:
                with self.assertRaises(PathSafetyError):
                    with root.lease(link / 'file.txt'):
                        self.fail('Retargeted root acquired a lease')
                self.assertEqual(list((base / 'second').iterdir()), [])
            finally:
                os.rmdir(link)

    def test_root_binding_survives_restart_and_allows_explicit_new_selection(self):
        from backend.settings import AppSettings, DirectorySettings, SettingsStore, load_effective_settings
        from backend.settings.directories import bind_directories
        from dataclasses import replace
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            for name in ['original', 'replacement']:
                (base / name).mkdir()
            configured = base / 'input'
            self.junction(configured, base / 'original')
            store = SettingsStore(base / 'settings.ini', AppSettings(directories=DirectorySettings(
                configured, base / 'output', base / 'archive', base / 'transcripts')))
            first = load_effective_settings(store)
            os.rmdir(configured)
            self.junction(configured, base / 'replacement')
            try:
                restarted = load_effective_settings(SettingsStore(store.path))
                binding = restarted.directories.binding(configured)
                self.assertEqual(binding, first.directories.binding(configured))
                with self.assertRaises(PathSafetyError):
                    binding.check()
                selected = bind_directories(replace(restarted.directories, input=base / 'replacement'))
                selected.binding(base / 'replacement').check()
            finally:
                os.rmdir(configured)

    def test_another_process_cannot_turn_leased_parent_into_a_junction(self):
        import ctypes
        from ctypes import wintypes
        from backend.filesystem.windows import Handle, _kernel
        _kernel.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                                            ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
        _kernel.DeviceIoControl.restype = wintypes.BOOL
        script = '''import ctypes,sys
from ctypes import wintypes
from backend.filesystem.windows import _kernel
_kernel.DeviceIoControl.argtypes=[wintypes.HANDLE,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(wintypes.DWORD),ctypes.c_void_p]
raw=bytes.fromhex(sys.argv[2]); data=ctypes.create_string_buffer(raw); returned=wintypes.DWORD()
handle=_kernel.CreateFileW(sys.argv[1],0x40000000,7,None,3,0x02200000,None)
if handle==ctypes.c_void_p(-1).value: sys.exit(3)
try: result=_kernel.DeviceIoControl(handle,0x900a4,data,len(raw),None,0,ctypes.byref(returned),None)
finally: _kernel.CloseHandle(handle)
sys.exit(0 if result else 2)
'''
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = RootBinding.capture(base / 'root')
            outside = base / 'outside'
            outside.mkdir()
            template = base / 'template'
            self.junction(template, outside)
            data = ctypes.create_string_buffer(16384)
            returned = wintypes.DWORD()
            with Handle(template, directory=True) as handle:
                self.assertTrue(_kernel.DeviceIoControl(handle.value, 0x900a8, None, 0, data, len(data), ctypes.byref(returned), None))
            payload = data.raw[:returned.value].hex()
            parent = root.configured / 'parent'
            parent.mkdir()
            try:
                with root.lease(parent / 'output.mp4'):
                    attempt = subprocess.run([sys.executable, '-c', script, str(parent), payload], capture_output=True, timeout=10)
                    self.assertEqual(attempt.returncode, 2, attempt.stderr)
                    self.assertEqual(list(outside.iterdir()), [])
                # The exact same native operation succeeds after the lease is released.
                control = subprocess.run([sys.executable, '-c', script, str(parent), payload], capture_output=True, timeout=10)
                self.assertEqual(control.returncode, 0, control.stderr)
                with self.assertRaises(PathSafetyError):
                    root.target(parent / 'output.mp4')
            finally:
                os.rmdir(parent)
                os.rmdir(template)
