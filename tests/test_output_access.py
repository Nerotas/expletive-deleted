import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from tests.media_fixtures import provenance
from backend.jobs.media import legacy_output_path, output_path
from backend.media_identity import MediaIdentityError, provenance_path

from backend.desktop.native_files import NativeFiles, NativeFileError
from backend.filesystem.paths import PathSafetyError
from backend.filesystem.publication import PublicationError
from backend.service.outputs import OutputAccessError
from backend.settings import AppSettings, DirectorySettings
from backend.settings.directories import bind_directories


@unittest.skipUnless(os.name == 'nt', 'Windows native file leases')
class OutputAccessTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        directories = bind_directories(DirectorySettings(*(self.root / name for name in ['input', 'output', 'archive', 'transcripts'])))
        self.settings = replace(AppSettings(), directories=directories)
        self.service = SimpleNamespace(settings=self.settings, output_context=lambda: (self.settings, []))
        self.policy = MagicMock()
        self.policy.export_payload.return_value = {'schema_version': 2, 'words': ['synthetic']}
        self.native = NativeFiles(self.service, self.policy)
        self.addCleanup(self.native.close)
        self.source = directories.input / 'film.mp4'
        self.source.write_bytes(b'original')
        self.output = output_path(self.source, directories.output)
        self.output.write_bytes(b'synthetic output')
        provenance(self.source, self.output)
        self.probe = self.enterContext(patch('backend.service.outputs.verify_playback'))

    def prepare(self, source=None):
        return self.native.handle('native.output.prepare', {'source': str(source or self.source)})['token']

    def test_export_cannot_replace_managed_dictionary_or_journal(self):
        from backend.policy import PolicyFileError, PolicyStore
        self.native.policy_store = PolicyStore(self.root / 'dictionary')
        self.native.policy_store.load()
        before = self.native.policy_store.censor_path.read_bytes()
        for name in ('censored.json', 'exclusions.json', 'discovered.json', '.policy-journal.json'):
            with self.assertRaises(PolicyFileError):
                self.native.handle('native.export.prepare', {
                    'destination': str(self.root / 'dictionary' / name),
                })
        self.assertEqual(self.native.policy_store.censor_path.read_bytes(), before)

    def test_output_is_derived_and_pinned_until_handoff(self):
        token = self.prepare()
        self.assertEqual(self.native.handle('native.output.check', {'token': token}), {'path': str(self.output)})
        with self.assertRaises(OSError):
            self.output.rename(self.output.with_suffix('.old'))
        with self.assertRaises(OSError):
            self.output.write_bytes(b'changed')
        self.native.release(token)
        self.output.rename(self.output.with_suffix('.old'))

    def test_previous_full_filename_output_remains_playable(self):
        previous = legacy_output_path(self.source, self.settings.directories.output)
        previous_sidecar = provenance_path(previous)
        self.output.rename(previous)
        provenance_path(self.output).rename(previous_sidecar)

        token = self.prepare()
        self.assertEqual(self.native.handle('native.output.check', {'token': token}), {'path': str(previous)})
        self.native.release(token)

    def test_audio_and_archived_job_source(self):
        source = self.source.with_suffix('.wav')
        source.write_bytes(b'audio')
        output = output_path(source, self.settings.directories.output)
        output.write_bytes(b'audio output')
        provenance(source, output)
        token = self.prepare(source)
        self.assertEqual(self.native.handle('native.output.check', {'token': token})['path'], str(output))
        self.native.release(token)
        self.source.rename(self.settings.directories.archive / self.source.name)
        job = SimpleNamespace(source=self.source, mode='censor', status='completed')
        self.service.output_context = lambda: (self.settings, [job])
        self.native.release(self.prepare())

    def test_arbitrary_paths_extensions_streams_and_missing_sources_are_rejected(self):
        for source in [self.root / 'outside.mp4', self.source.parent / 'absent.mp4',
                       self.source.parent / '../outside.mp4', *[self.source.with_suffix(ext) for ext in ['.exe', '.cmd', '.bat', '.lnk', '.url']],
                       Path(str(self.source) + ':stream')]:
            with self.subTest(source=source), self.assertRaises((ValueError, OutputAccessError)):
                self.prepare(source)
        self.probe.assert_not_called()

    def test_empty_missing_alias_and_failed_verification_release_leases(self):
        self.output.unlink()
        with self.assertRaises(OutputAccessError): self.prepare()
        self.output.touch()
        with self.assertRaises((OutputAccessError, MediaIdentityError)): self.prepare()
        self.output.unlink()
        os.link(self.source, self.output)
        with self.assertRaises(PathSafetyError): self.prepare()
        self.output.unlink()
        self.output.write_bytes(b'output')
        self.probe.side_effect = OutputAccessError('verification failed')
        with self.assertRaises((OutputAccessError, MediaIdentityError)): self.prepare()
        self.output.write_bytes(b'unlocked')

    def test_expiration_close_and_changed_settings(self):
        self.native.lease_seconds = 0.05
        token = self.prepare()
        expired = Event()
        # The timer itself must close the handles, without a later request doing cleanup.
        self.native._leases[token]['resources'].callback(expired.set)
        self.assertTrue(expired.wait(2))
        with self.assertRaises(NativeFileError): self.native.handle('native.output.check', {'token': token})
        self.native.lease_seconds = 30
        token = self.prepare()
        self.service.settings = replace(self.settings, directories=replace(self.settings.directories, output=self.root / 'other'))
        with self.assertRaises(PathSafetyError): self.native.handle('native.output.check', {'token': token})
        self.native.close()
        self.output.write_bytes(b'unlocked')

    def test_junction_escape_and_root_retarget_are_rejected(self):
        import _winapi
        outside = self.root / 'outside'
        outside.mkdir()
        (outside / 'nested-censored.mkv').write_bytes(b'outside')
        (self.source.parent / 'linked').mkdir()
        source = self.source.parent / 'linked' / 'nested.mp4'
        source.write_bytes(b'original')
        link = self.output.parent / 'linked'
        _winapi.CreateJunction(str(outside), str(link))
        try:
            with self.assertRaises(PathSafetyError): self.prepare(source)
        finally:
            os.rmdir(link)
        moved = self.root / 'previous-output'
        self.output.parent.rename(moved)
        _winapi.CreateJunction(str(outside), str(self.output.parent))
        try:
            with self.assertRaises(PathSafetyError): self.prepare()
        finally:
            os.rmdir(self.output.parent)

    def test_export_creation_replacement_and_one_use_token(self):
        target = self.root / 'backup.json'
        for existing in [False, True]:
            selection = self.native.handle('native.export.prepare', {'destination': str(target)})
            self.assertEqual(selection['exists'], existing)
            result = self.native.handle('native.dictionary.export', {**selection, 'overwrite': existing})
            self.assertEqual(result['path'], str(target))
            self.assertEqual(json.loads(target.read_text()), self.policy.export_payload.return_value)
            with self.assertRaises(NativeFileError): self.native.handle('native.dictionary.export', selection)

    def test_export_conflicts_and_missing_confirmation_preserve_sentinels(self):
        target = self.root / 'backup.json'
        for initial, confirm in [(False, False), (True, False), (True, True)]:
            target.unlink(missing_ok=True)
            if initial: target.write_bytes(b'original')
            selection = self.native.handle('native.export.prepare', {'destination': str(target)})
            target.write_bytes(b'competing replacement')
            with self.assertRaises((NativeFileError, PathSafetyError, PublicationError)):
                self.native.handle('native.dictionary.export', {**selection, 'overwrite': confirm})
            self.assertEqual(target.read_bytes(), b'competing replacement')

    def test_import_only_reads_selected_json_and_exports_reject_other_extensions(self):
        for method, key in [('native.dictionary.import', 'source'), ('native.export.prepare', 'destination')]:
            with self.assertRaises(NativeFileError): self.native.handle(method, {key: str(self.root / 'bad.exe')})
        self.policy.import_dictionary.assert_not_called()
        target = self.root / 'backup.json'
        target.write_text('{}')
        self.native.handle('native.dictionary.import', {'source': str(target)})
        self.policy.import_dictionary.assert_called_once_with(target)


class PlaybackVerifierTests(unittest.TestCase):
    def test_bounded_probe_requires_streams_and_blocks_network_protocols(self):
        from backend.service.outputs import verify_playback
        with self.assertRaises(OutputAccessError): verify_playback(Path('output.mkv'), None)
        for streams, valid in [(['audio', 'video'], True), (['audio'], False), ([], False)]:
            with patch('backend.service.outputs.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout=json.dumps({'streams': [{'codec_type': x} for x in streams]}))) as run:
                if valid: verify_playback(Path('output.mkv'), 'ffprobe')
                else:
                    with self.assertRaises(OutputAccessError): verify_playback(Path('output.mkv'), 'ffprobe')
                self.assertEqual(run.call_args.kwargs['timeout'], 15)
                self.assertIn('file,pipe', run.call_args.args[0])
