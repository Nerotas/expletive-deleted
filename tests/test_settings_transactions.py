"""Settings edits retain concurrent values across threads and Python processes."""
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

from backend.settings import AppSettings, SettingsStore, SettingsValidationError
from backend.settings.resolver import effective_settings
from backend.settings.transactions import changes_between, snapshot, validate_base
from backend.service import BackendService


class SettingsTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.store = SettingsStore(self.root / 'settings.ini', AppSettings.defaults(self.root / 'media'))
        self.base = self.store.snapshot()

    def change(self, field, value, base=None):
        base = base or self.base
        group, key = field.split('.')
        return {'field': field, 'expected': base['settings'][group][key], 'value': value}

    def test_unrelated_settings_and_progress_survive_both_directions(self):
        self.store.transact(self.base['revision'], [self.change('runtime.ytdlp_path', str(self.root / 'yt-dlp.exe'))])
        draft = copy.deepcopy(self.base['settings'])
        draft['onboarding']['last_step'] = 'settings'
        result = self.store.transact(self.base['revision'], changes_between(self.base['settings'], draft))
        self.assertEqual(result['status'], 'saved')
        self.assertEqual(result['snapshot']['settings']['runtime']['ytdlp_path'], str(self.root / 'yt-dlp.exe'))
        self.store.transact(self.base['revision'], [self.change('runtime.whisper_cache', str(self.root / 'model'))])
        self.assertEqual(self.store.load().onboarding.last_step, 'settings')

    def test_conflict_writes_nothing_and_returns_expected_current_proposed(self):
        self.store.transact(self.base['revision'], [self.change('censoring.padding_before_ms', 250)])
        before = self.store.path.read_bytes()
        result = self.store.transact(self.base['revision'], [self.change('censoring.padding_before_ms', 500), self.change('processing.device', 'cpu')])
        self.assertEqual(result['status'], 'conflict')
        self.assertEqual(result['conflicts'], [{'field': 'censoring.padding_before_ms', 'expected': 150, 'current': 250, 'proposed': 500}])
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertEqual(result['snapshot'], self.store.snapshot())

    def test_resolution_checks_revision_even_for_unrelated_or_already_satisfied_change(self):
        current = self.store.transact(self.base['revision'], [self.change('processing.device', 'cpu')])['snapshot']
        self.store.transact(current['revision'], [self.change('onboarding.last_step', 'components', current)])
        result = self.store.transact(current['revision'], [self.change('processing.device', 'cpu', current)], strict=True)
        self.assertEqual(result['status'], 'conflict')

    def test_same_proposal_is_idempotent(self):
        changes = [self.change('processing.device', 'cpu')]
        for _ in range(2):
            self.assertEqual(self.store.transact(self.base['revision'], changes)['status'], 'saved')

    def test_invalid_fields_values_and_merged_result_do_not_write(self):
        cases = [
            [self.change('processing.device', 'invalid')],
            [self.change('censoring.padding_before_ms', True)],
            [self.change('directories.input', self.base['settings']['directories']['output'])],
            [self.change('processing.device', 'cpu')] * 2,
            [{'field': 'schema_version', 'expected': 1, 'value': 2}],
            [{'field': 'runtime.shell', 'expected': None, 'value': 'x'}],
        ]
        before = self.store.path.read_bytes()
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.store.transact(self.base['revision'], changes)
            self.assertEqual(before, self.store.path.read_bytes())

    def test_coordinated_directory_swap_validates_entire_merge(self):
        result = self.store.transact(self.base['revision'], [
            self.change('directories.input', self.base['settings']['directories']['output']),
            self.change('directories.output', self.base['settings']['directories']['input']),
        ])
        self.assertEqual(result['status'], 'saved')

    def test_snapshot_revision_validates_complete_baseline(self):
        self.assertEqual(validate_base(self.base), self.base)
        invalid = copy.deepcopy(self.base)
        invalid['settings']['processing']['device'] = 'cpu'
        with self.assertRaises(ValueError):
            validate_base(invalid)
        with self.assertRaises(ValueError):
            validate_base(None)

    def test_effective_override_is_described_but_never_persisted(self):
        original = self.store.load().directories
        with patch.dict(os.environ, {'CENSOR_PROJECT_ROOT': str(self.root / 'override')}):
            base = self.store.snapshot(effective_settings)
            self.assertNotEqual(base['revision'], self.base['revision'])
            self.assertEqual(base, snapshot(effective_settings(self.store.load())))
            result = self.store.transact(base['revision'], [self.change('processing.device', 'cpu', base)], effective=effective_settings)
            self.assertEqual(result['status'], 'saved')
            self.assertEqual(self.store.load().directories, original)
            with self.assertRaisesRegex(SettingsValidationError, 'override'):
                self.store.transact(base['revision'], [self.change('directories.input', str(self.root / 'other'), base)], effective=effective_settings)

    def test_two_store_objects_merge_under_thread_lock(self):
        barrier = Barrier(2)
        def edit(field, value):
            store = SettingsStore(self.store.path)
            base = store.snapshot()
            barrier.wait(5)
            return store.transact(base['revision'], [self.change(field, value, base)])
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(edit, 'processing.device', 'cpu')
            b = pool.submit(edit, 'onboarding.last_step', 'components')
            self.assertEqual(a.result(10)['status'], 'saved')
            self.assertEqual(b.result(10)['status'], 'saved')
        self.assertEqual(self.store.load().processing.device, 'cpu')
        self.assertEqual(self.store.load().onboarding.last_step, 'components')

    def test_independent_processes_merge_from_same_baseline(self):
        code = '''import json,sys
from pathlib import Path
from backend.settings import SettingsStore
store=SettingsStore(Path(sys.argv[1]))
base=store.snapshot()
print('ready', flush=True)
sys.stdin.readline()
field,value=sys.argv[2:]
group,key=field.split('.')
print(json.dumps(store.transact(base['revision'], [{'field':field,'expected':base['settings'][group][key],'value':value}])), flush=True)
'''
        children = [subprocess.Popen([sys.executable, '-c', code, str(self.store.path), field, value], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    for field, value in [('processing.device', 'cpu'), ('onboarding.last_step', 'components')]]
        try:
            for child in children:
                self.assertEqual(child.stdout.readline().strip(), 'ready')
            for child in children:
                child.stdin.write('go\n'); child.stdin.flush()
            for child in children:
                output, error = child.communicate(timeout=15)
                self.assertEqual(child.returncode, 0, error)
                self.assertEqual(json.loads(output)['status'], 'saved')
        finally:
            for child in children:
                if child.poll() is None: child.kill()
                child.communicate()
        self.assertEqual(self.store.load().processing.device, 'cpu')
        self.assertEqual(self.store.load().onboarding.last_step, 'components')

    def test_cli_cannot_bypass_desktop_guards(self):
        env = {key: value for key, value in os.environ.items() if not key.startswith('CENSOR_')}
        env['CENSOR_APP_DATA_DIR'] = str(self.root)
        before = self.store.path.read_bytes()
        with self.store.desktop_owner():
            result = subprocess.run([sys.executable, 'manage_settings.py', 'set-options', '--device', 'cpu'], env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 1)
        self.assertIn('Close the desktop', result.stdout)
        self.assertEqual(before, self.store.path.read_bytes())
        result = subprocess.run([sys.executable, 'manage_settings.py', 'set-options', '--device', 'cpu'], env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.store.load().processing.device, 'cpu')

    def test_failed_persistence_or_manager_construction_preserves_live_state(self):
        service = BackendService(self.store)
        self.addCleanup(service.close)
        original_jobs, original_downloads = service.jobs, service.downloads
        before = self.store.path.read_bytes()
        for target in ('backend.settings.store.os.replace', 'backend.service.application.DownloadManager'):
            with self.subTest(target=target), patch(target, side_effect=OSError('disk/constructor failure')), self.assertRaises(Exception):
                service.patch_settings(self.base['revision'], [self.change('processing.device', 'cpu')])
            self.assertIs(service.jobs, original_jobs)
            self.assertIs(service.downloads, original_downloads)
            self.assertEqual(service.settings.processing.device, 'auto')
            self.assertEqual(self.store.path.read_bytes(), before)

    def test_rejects_incomplete_update_instead_of_filling_missing_fields_with_defaults(self):
        with self.assertRaisesRegex(ValueError, "complete draft"):
            changes_between(self.base["settings"], {"processing": {"device": "cpu"}})

    def test_flush_failure_removes_temporary_file_and_preserves_original(self):
        before = self.store.path.read_bytes()
        with patch('backend.settings.store.os.fsync', side_effect=OSError('flush failed')), self.assertRaises(Exception):
            self.store.transact(self.base['revision'], [self.change('processing.device', 'cpu')])
        self.assertEqual(before, self.store.path.read_bytes())
        self.assertEqual(list(self.root.glob('.settings.ini.*.tmp')), [])
