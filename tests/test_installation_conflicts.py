"""Offline setup/inspection races and retry-only settings resolution."""
import copy
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.desktop.installation import InstallationController
from backend.jobs.downloads import DownloadRecord
from backend.runtime.dependency_models import InstallResult
from backend.service import BackendService
from backend.settings import AppSettings, SettingsStore


class InstallationConflictTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.service = BackendService(SettingsStore(self.root / 'settings.ini', AppSettings.defaults(self.root / 'media')))
        self.addCleanup(self.service.close)
        self.controller = InstallationController(self.service)
        self.controller._install_executor.shutdown()
        self.controller._install_executor = MagicMock()
        self.ready = SimpleNamespace(ready=True, path=self.root / 'verified.exe', detail='verified', installed_version='8.0')
        for target in ('inspect_executable', 'inspect_whisper_model', 'inspect_ytdlp'):
            patcher = patch(f'backend.desktop.installation.{target}', return_value=self.ready)
            patcher.start(); self.addCleanup(patcher.stop)
        patcher = patch('backend.desktop.installation.get_application_runtime_root', return_value=self.root / 'runtime')
        patcher.start(); self.addCleanup(patcher.stop)

    def edit(self, group, key, value):
        base = self.service.get_settings_snapshot()
        return self.service.patch_settings(base['revision'], [{'field': f'{group}.{key}', 'expected': base['settings'][group][key], 'value': value}])

    def plan(self, component):
        payload = self.controller.handle('dependencies.plan', {'components': [component]})
        started = self.controller.handle('dependencies.install', {'plan_id': payload['plan_id']})
        return self.controller._install_plans[payload['plan_id']], started['install_id']

    def complete(self, plan, operation):
        context = self.controller._install_jobs[operation]['context']
        result = tuple(InstallResult(action.id, action.dependency_ids, 'verified') for action in plan.actions)
        with patch('backend.desktop.installation.execute_install_plan', return_value=result) as execute:
            self.controller._run_install_task(operation, plan.id, plan, context.cache_dir)
        self.assertEqual(execute.call_args.kwargs['cache_dir'], context.cache_dir)
        return self.controller.handle('dependencies.status', {'install_id': operation})

    def resolve(self, state, choice='use_verified'):
        with patch('backend.desktop.installation.execute_install_plan') as execute:
            result = self.controller.handle('dependencies.resolve_conflict', {
                'install_id': state['install_id'], 'revision': state['resolution']['snapshot']['revision'],
                'choices': {key: choice for key in state['verified_values']},
            })
        execute.assert_not_called()
        return result

    def test_setup_preserves_newer_preferences_progress_and_other_components(self):
        plan, operation = self.plan('whisper_model')
        self.edit('processing', 'device', 'cpu')
        self.edit('onboarding', 'last_step', 'settings')
        self.edit('runtime', 'ytdlp_path', str(self.root / 'manual.exe'))
        state = self.complete(plan, operation)
        self.assertEqual(state['status'], 'completed')
        saved = self.service.store.load()
        self.assertEqual(saved.processing.device, 'cpu')
        self.assertEqual(saved.onboarding.last_step, 'settings')
        self.assertEqual(saved.runtime.ytdlp_path, self.root / 'manual.exe')
        self.assertEqual(self.service.jobs.settings, self.service.settings)
        self.assertEqual(self.service.downloads.settings, self.service.settings)

    def test_cache_destination_and_expectations_are_captured_at_plan_creation(self):
        payload = self.controller.handle('dependencies.plan', {'components': ['whisper_model']})
        context = self.controller._plan_contexts[payload['plan_id']]
        self.edit('runtime', 'whisper_cache', str(self.root / 'new-choice'))
        operation = self.controller.handle('dependencies.install', {'plan_id': payload['plan_id']})['install_id']
        self.assertEqual(self.controller._install_executor.submit.call_args.args[-1], context.cache_dir)
        state = self.complete(self.controller._install_plans[payload['plan_id']], operation)
        self.assertEqual(state['status'], 'awaiting_resolution')
        self.assertEqual(self.service.store.load().runtime.whisper_cache, self.root / 'new-choice')
        self.assertEqual(state['verified_values']['runtime.whisper_cache'], str(context.cache_dir))

    def test_same_field_conflict_writes_nothing_and_both_choices_work(self):
        for choice in ('keep_current', 'use_verified'):
            with self.subTest(choice=choice):
                # A fresh controller represents another explicitly reviewed operation.
                self.controller._install_plans.clear(); self.controller._plan_contexts.clear(); self.controller._install_jobs.clear()
                plan, operation = self.plan('ytdlp')
                manual = self.root / f'{choice}.exe'
                self.edit('runtime', 'ytdlp_path', str(manual))
                before = self.service.store.path.read_bytes()
                state = self.complete(plan, operation)
                self.assertEqual(state['status'], 'awaiting_resolution')
                self.assertEqual(before, self.service.store.path.read_bytes())
                resolved = self.resolve(state, choice)
                self.assertEqual(resolved['status'], 'completed')
                expected = str(manual) if choice == 'keep_current' else state['verified_values']['runtime.ytdlp_path']
                self.assertEqual(str(self.service.store.load().runtime.ytdlp_path), expected)

    def test_another_edit_during_resolution_requires_new_choice(self):
        plan, operation = self.plan('ytdlp')
        self.edit('runtime', 'ytdlp_path', str(self.root / 'manual.exe'))
        state = self.complete(plan, operation)
        self.edit('processing', 'device', 'cpu')
        result = self.resolve(state)
        self.assertEqual(result['status'], 'awaiting_resolution')
        self.assertNotEqual(result['resolution']['snapshot']['revision'], state['resolution']['snapshot']['revision'])
        self.assertEqual(self.service.store.load().runtime.ytdlp_path, self.root / 'manual.exe')
        self.assertEqual(self.resolve(result)['status'], 'completed')
        self.assertEqual(self.service.store.load().processing.device, 'cpu')

    def test_resolution_revalidates_and_keeps_files_when_component_becomes_invalid(self):
        plan, operation = self.plan('ytdlp')
        self.edit('runtime', 'ytdlp_path', str(self.root / 'manual.exe'))
        state = self.complete(plan, operation)
        artifact = Path(state['verified_values']['runtime.ytdlp_path'])
        artifact.parent.mkdir(parents=True); artifact.write_bytes(b'completed download')
        self.ready.ready = False
        result = self.resolve(state)
        self.assertEqual(result['status'], 'awaiting_resolution')
        self.assertIn('not ready', result['error'])
        self.assertEqual(artifact.read_bytes(), b'completed download')

    def test_repeated_approval_does_not_reinstall_while_waiting(self):
        plan, operation = self.plan('ytdlp')
        self.edit('runtime', 'ytdlp_path', str(self.root / 'manual.exe'))
        self.complete(plan, operation)
        again = self.controller.handle('dependencies.install', {'plan_id': plan.id})
        self.assertEqual(again['install_id'], operation)
        self.controller._install_executor.submit.assert_called_once()
        self.assertEqual(self.controller.handle('dependencies.cancel', {'install_id': operation})['status'], 'awaiting_resolution')

    def test_active_download_and_disk_failure_retain_verified_operation_for_retry(self):
        plan, operation = self.plan('ytdlp')
        self.service.downloads._records['download'] = DownloadRecord('download', 'url', 'id', status='downloading')
        state = self.complete(plan, operation)
        self.assertEqual(state['status'], 'awaiting_resolution')
        self.assertIn('active', state['error'])
        self.service.downloads._records.clear()
        with patch('backend.settings.store.os.replace', side_effect=OSError('disk full')):
            state = self.resolve(state)
        self.assertEqual(state['status'], 'awaiting_resolution')
        self.assertIn('disk full', state['error'])
        self.assertEqual(self.resolve(state)['status'], 'completed')
        self.controller._install_executor.submit.assert_called_once()

    def test_concurrent_component_completions_preserve_each_other(self):
        model, model_id = self.plan('whisper_model')
        ytdlp, ytdlp_id = self.plan('ytdlp')
        contexts = [self.controller._install_jobs[item]['context'] for item in (model_id, ytdlp_id)]
        def execute(plan, **kwargs):
            return tuple(InstallResult(action.id, action.dependency_ids, 'verified') for action in plan.actions)
        with patch('backend.desktop.installation.execute_install_plan', side_effect=execute), ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(self.controller._run_install_task, model_id, model.id, model, contexts[0].cache_dir)
            b = pool.submit(self.controller._run_install_task, ytdlp_id, ytdlp.id, ytdlp, contexts[1].cache_dir)
            a.result(10); b.result(10)
        settings = self.service.store.load()
        self.assertIsNotNone(settings.runtime.ytdlp_path)
        self.assertEqual(settings.runtime.whisper_cache, contexts[0].cache_dir)

    def test_paused_inspection_preserves_newer_values_and_detects_manual_path(self):
        entered, release = Event(), Event()
        def inspect(*args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(10))
            return self.ready
        with patch('backend.desktop.installation.inspect_ytdlp', side_effect=inspect), ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.controller.handle, 'dependencies.locate_ytdlp', {'path': str(self.root / 'verified.exe')})
            self.assertTrue(entered.wait(10))
            self.edit('processing', 'device', 'cpu')
            self.edit('onboarding', 'last_step', 'components')
            self.edit('runtime', 'ytdlp_path', str(self.root / 'manual.exe'))
            release.set()
            state = future.result(10)
        self.assertEqual(state['status'], 'awaiting_resolution')
        self.assertEqual(self.resolve(state)['status'], 'completed')
        self.assertEqual(self.service.store.load().processing.device, 'cpu')
        self.assertEqual(self.service.store.load().onboarding.last_step, 'components')

    def test_ffmpeg_pair_conflict_never_saves_half_a_pair(self):
        entered, release = Event(), Event()
        def inspect(*args, **kwargs):
            entered.set(); self.assertTrue(release.wait(10)); return self.ready
        with patch('backend.desktop.installation.inspect_executable', side_effect=inspect), ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.controller.handle, 'dependencies.locate_ffmpeg', {'path': str(self.root / 'verified' / 'ffmpeg.exe')})
            self.assertTrue(entered.wait(10))
            self.edit('runtime', 'ffmpeg_path', str(self.root / 'manual' / 'ffmpeg.exe'))
            before = self.service.store.path.read_bytes()
            release.set(); state = future.result(10)
        self.assertEqual(state['status'], 'awaiting_resolution')
        self.assertEqual(before, self.service.store.path.read_bytes())
        with self.assertRaisesRegex(ValueError, 'together'):
            self.controller.handle('dependencies.resolve_conflict', {'install_id': state['install_id'], 'revision': state['resolution']['snapshot']['revision'],
                'choices': {'runtime.ffmpeg_path': 'keep_current', 'runtime.ffprobe_path': 'use_verified'}})
        self.assertEqual(self.resolve(state)['status'], 'completed')
        self.assertEqual(self.service.store.load().runtime.ffprobe_path.parent, self.service.store.load().runtime.ffmpeg_path.parent)

    def test_model_change_during_setup_requires_fresh_model_verification(self):
        plan, operation = self.plan('whisper_model')
        self.edit('whisper', 'model', 'small')
        state = self.complete(plan, operation)
        self.assertEqual(state['status'], 'awaiting_resolution')
        with patch('backend.desktop.installation.inspect_whisper_model', return_value=self.ready) as inspect:
            self.assertEqual(self.resolve(state)['status'], 'completed')
        self.assertEqual(inspect.call_args.kwargs['model'], 'small')
        self.assertEqual(self.service.settings.whisper.model, 'small')
