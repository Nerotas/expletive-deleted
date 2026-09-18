import os
import tempfile
import unittest
import subprocess
import sys
from pathlib import Path
from threading import Event
from unittest.mock import patch

from backend.filesystem.paths import PathSafetyError, RootBinding
from backend.filesystem.publication import Publication, PublicationError, move_verified


@unittest.skipUnless(os.name == 'nt', 'Native publication gate')
class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = RootBinding.capture(Path(self.temporary.name) / 'root')
        self.destination = self.root.configured / 'output.mp4'

    def test_new_and_authorized_replacement(self):
        for overwrite, content in [(False, b'new'), (True, b'replacement')]:
            with Publication(self.root, self.destination, overwrite=overwrite) as output:
                output.stage.write_bytes(content)
                output.publish(lambda _: None)
            self.assertEqual(self.destination.read_bytes(), content)
        self.assertEqual(list(self.root.configured.iterdir()), [self.destination])

    def test_queued_copy_rejects_changed_source_without_touching_it(self):
        from backend.filesystem.paths import version
        from backend.filesystem.publication import copy_verified
        source = self.root.configured / 'source.mp4'
        source.write_bytes(b'original')
        selected = version(source)
        source.write_bytes(b'changed by its owner')
        with self.assertRaises(PathSafetyError):
            with Publication(self.root, self.destination, source=source) as output:
                copy_verified(source, output, expected_version=selected)
        self.assertEqual(source.read_bytes(), b'changed by its owner')
        self.assertFalse(self.destination.exists())

    def test_failed_verification_cancel_and_flush_preserve_original(self):
        self.destination.write_bytes(b'previous')
        for fault in ['verify', 'cancel', 'flush']:
            with self.subTest(fault=fault), self.assertRaises((RuntimeError, InterruptedError, OSError)):
                cancellation = Event()
                with Publication(self.root, self.destination, overwrite=True, cancellation=cancellation) as output:
                    output.stage.write_bytes(b'partial')
                    def verify(_):
                        if fault == 'verify':
                            raise RuntimeError('Invalid streams')
                        if fault == 'cancel':
                            cancellation.set()
                    if fault == 'flush':
                        with patch('os.fsync', side_effect=OSError('Disk full')):
                            output.publish(verify)
                    else:
                        output.publish(verify)
            self.assertEqual(self.destination.read_bytes(), b'previous')
            self.assertEqual(list(self.root.configured.iterdir()), [self.destination])

    def test_collision_preserves_winner_and_cleans_only_own_stage(self):
        with self.assertRaises(PublicationError):
            with Publication(self.root, self.destination) as loser:
                loser.stage.write_bytes(b'loser')
                self.destination.write_bytes(b'winner')
                loser.publish(lambda _: None)
        self.assertEqual(self.destination.read_bytes(), b'winner')
        self.assertEqual(list(self.root.configured.iterdir()), [self.destination])

    def test_changed_authorized_target_is_not_replaced(self):
        self.destination.write_bytes(b'previous')
        with self.assertRaises(PathSafetyError):
            with Publication(self.root, self.destination, overwrite=True) as output:
                output.stage.write_bytes(b'new')
                self.destination.rename(self.destination.with_suffix('.old'))
                self.destination.write_bytes(b'other writer')
                output.publish(lambda _: None)
        self.assertEqual(self.destination.read_bytes(), b'other writer')

    def test_source_move_keeps_bytes(self):
        source_root = RootBinding.capture(Path(self.temporary.name) / 'source')
        source = source_root.configured / 'original.mp4'
        source.write_bytes(b'original')
        move_verified(source_root, source, self.root, self.destination)
        self.assertFalse(source.exists())
        self.assertEqual(self.destination.read_bytes(), b'original')

    def test_source_alias_and_empty_stage_are_rejected(self):
        self.destination.write_bytes(b'original')
        with self.assertRaises(PathSafetyError):
            with Publication(self.root, self.destination, source=self.destination, overwrite=True):
                self.fail('Source alias accepted')
        other = self.root.configured / 'empty.mp4'
        with self.assertRaises(PublicationError):
            with Publication(self.root, other) as output:
                output.publish(lambda _: None)
        self.assertFalse(other.exists())

    def test_failed_replacement_restores_old_output(self):
        from backend.filesystem.windows import Handle
        self.destination.write_bytes(b'previous')
        original_rename = Handle.rename
        def fail_staging(handle, destination):
            if '.partial' in handle.path.name:
                raise OSError('Injected rename failure')
            return original_rename(handle, destination)
        with self.assertRaises(OSError), patch.object(Handle, 'rename', fail_staging):
            with Publication(self.root, self.destination, overwrite=True) as output:
                output.stage.write_bytes(b'new')
                output.publish(lambda _: None)
        self.assertEqual(self.destination.read_bytes(), b'previous')
        self.assertEqual(list(self.root.configured.iterdir()), [self.destination])

    def test_replacement_conflict_retains_recovery_without_deleting_competitor(self):
        from backend.filesystem.windows import Handle
        self.destination.write_bytes(b'previous')
        original_rename = Handle.rename
        def competing_writer(handle, destination):
            if '.partial' in handle.path.name:
                destination.write_bytes(b'competing result')
            return original_rename(handle, destination)
        with self.assertRaisesRegex(PublicationError, 'previous output retained at'), patch.object(Handle, 'rename', competing_writer):
            with Publication(self.root, self.destination, overwrite=True) as output:
                output.stage.write_bytes(b'new')
                output.publish(lambda _: None)
        self.assertEqual(self.destination.read_bytes(), b'competing result')
        backups = list(self.root.configured.glob('*.recovery'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), b'previous')

    def test_two_processes_cannot_both_publish_same_name(self):
        script = '''import sys,time
from pathlib import Path
from backend.filesystem.paths import RootBinding
from backend.filesystem.publication import Publication
root=RootBinding.capture(Path(sys.argv[1]))
barrier=Path(sys.argv[2]); name=sys.argv[3]
try:
 with Publication(root,root.configured/'output.mp4') as output:
  output.stage.write_text(name)
  (barrier/name).touch()
  deadline=time.monotonic()+10
  while len(list(barrier.iterdir())) < 2:
   if time.monotonic()>deadline: raise RuntimeError('Barrier timed out')
   time.sleep(.01)
  output.publish(lambda _:None)
 print('won')
except Exception as error:
 print(type(error).__name__)
 sys.exit(2)
'''
        barrier = Path(self.temporary.name) / 'barrier'
        barrier.mkdir()
        processes = [subprocess.Popen([sys.executable, '-B', '-c', script, str(self.root.configured), str(barrier), name],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for name in ['one', 'two']]
        try:
            results = [process.communicate(timeout=15) for process in processes]
            self.assertEqual(sorted(process.returncode for process in processes), [0, 2], results)
            self.assertIn(self.destination.read_text(), ['one', 'two'])
            self.assertEqual(list(self.root.configured.iterdir()), [self.destination])
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.wait()
