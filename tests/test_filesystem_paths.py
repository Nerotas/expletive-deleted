import os
import tempfile
import unittest
from pathlib import Path

from backend.filesystem.paths import PathSafetyError, RootBinding, reject_alias, validate_path


class FilesystemPathTests(unittest.TestCase):
    def test_containment_and_aliases(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = RootBinding.capture(base / 'root')
            source = root.configured / 'source.mp4'
            source.write_bytes(b'original')
            alias = root.configured / 'alias.mp4'
            os.link(source, alias)
            with self.assertRaises(PathSafetyError):
                reject_alias(source, alias)
            for target in [base / 'root-sibling' / 'file.mp4', root.configured / '..' / 'outside.mp4']:
                with self.subTest(target=target), self.assertRaises(PathSafetyError):
                    root.target(target)

    def test_replaced_root_keeps_old_binding(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = RootBinding.capture(Path(temporary) / 'root')
            root.configured.rename(Path(temporary) / 'old')
            root.configured.mkdir()
            with self.assertRaises(PathSafetyError):
                root.target(root.configured / 'file')

    @unittest.skipUnless(os.name == 'nt', 'Windows path syntax')
    def test_windows_ambiguous_names_are_rejected(self):
        for value in [r'C:relative', r'\\?\C:\device', r'\\server\share\file',
                      r'C:\safe\file:stream', r'C:\safe\NUL.mp4', r'C:\safe\tail.', r'C:\safe\tail ']:
            with self.subTest(value=value), self.assertRaises(PathSafetyError):
                validate_path(Path(value))
