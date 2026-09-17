"""Run from the repo root: offline bridge probes using temporary data and mocks."""

import io
import json
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event, Lock
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path.cwd()))
from backend.policy import PolicyStore
from backend.service import BackendService
from backend.settings import AppSettings, DirectorySettings, SettingsStore
from scripts.desktop_bridge import DesktopBridge, serve

results = {}
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    defaults = root / 'defaults.txt'
    exclusions = root / 'exclusions.txt'
    defaults.write_text('baseline\n')
    exclusions.write_text('')
    policy = PolicyStore(root / 'dictionary', censor_defaults_path=defaults, exclusions_defaults_path=exclusions)
    policy.load()
    bridge = DesktopBridge(MagicMock(), policy)
    original_load = policy.load
    barrier, lock = Barrier(2), Lock()
    calls = [0]
    first_done = Event()
    def synchronized_load():
        snapshot = original_load()
        with lock:
            calls[0] += 1
            position = calls[0]
            initial = position <= 2
        if initial:
            barrier.wait(timeout=5)
            if position == 2:
                assert first_done.wait(5)
        return snapshot
    def update_word(word):
        try:
            return bridge.handle('dictionary.add', {'target': 'censor', 'word': word})
        finally:
            first_done.set()
    with patch.object(policy, 'load', side_effect=synchronized_load), ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(update_word, word) for word in ('auditone', 'audittwo')]
        outcomes = [future.result(timeout=10)['changed'] for future in futures]
    results['dictionary_concurrent_add'] = {'both_acknowledged': outcomes, 'retained': sorted(original_load().censor_words & {'auditone', 'audittwo'})}
    victim = root / 'original.mp4'
    victim.write_bytes(b'original synthetic media')
    bridge.handle('dictionary.export', {'destination': str(victim)})
    results['dictionary_export'] = {'existing_media_overwritten': victim.read_bytes() != b'original synthetic media', 'picker_used': False}
    bridge.close()

    settings = AppSettings(directories=DirectorySettings(root/'Ready', root/'Finished', root/'Processed', root/'Transcripts'))
    def manager_factory(settings):
        manager = MagicMock()
        manager.list.return_value = ()
        return manager
    service = BackendService(SettingsStore(root/'settings.ini', settings), manager_factory=manager_factory)
    bridge = DesktopBridge(service, policy)
    plan = SimpleNamespace(actions=[SimpleNamespace(id='model')])
    bridge._install_jobs['audit'] = {'cancel_event': Event()}
    original_get = service.get_settings
    snapshot_read, resume = Event(), Event()
    def paused_snapshot():
        snapshot = original_get()
        snapshot_read.set()
        assert resume.wait(5)
        return snapshot
    with patch('scripts.desktop_bridge.execute_install_plan', return_value=[SimpleNamespace(dependency_ids=['whisper:test'], action_id='model')]), patch.object(service, 'get_settings', side_effect=paused_snapshot), ThreadPoolExecutor(1) as pool:
        future = pool.submit(bridge._run_install_task, 'audit', 'plan', plan, root/'model')
        assert snapshot_read.wait(5)
        user_settings = original_get()
        user_settings['onboarding']['completed'] = True
        service.update_settings(user_settings)
        resume.set()
        future.result(timeout=10)
    results['setup_settings_race'] = {'saved_completed': True, 'retained_completed': original_get()['onboarding']['completed'], 'install_status': bridge._install_jobs['audit']['status']}
    bridge._install_plans['repeat'] = plan
    with patch.object(bridge._install_executor, 'submit') as submit:
        first = bridge.handle('dependencies.install', {'plan_id': 'repeat'})
        second = bridge.handle('dependencies.install', {'plan_id': 'repeat'})
    results['duplicate_setup'] = {'scheduled_workers': submit.call_count, 'distinct_install_ids': first['install_id'] != second['install_id']}
    # Freeze archive after its active-job check, then queue the same source.
    source = service.settings.directories.input / 'audit.mkv'
    source.write_bytes(b'original')
    checked, continue_archive = Event(), Event()
    def paused_library():
        checked.set()
        assert continue_archive.wait(5)
        return [SimpleNamespace(source=source, status='transcribed')]
    def queue_job(*args, **kwargs):
        service.jobs.list.return_value = (SimpleNamespace(source=source, status='queued'),)
        return SimpleNamespace(id='queued')
    service.jobs.submit.side_effect = queue_job
    with patch.object(service, 'get_library', side_effect=paused_library), ThreadPoolExecutor(1) as pool:
        future = pool.submit(service.archive_source, source)
        assert checked.wait(5)
        service.submit_job(source, 'report_only')
        continue_archive.set()
        future.result(timeout=10)
    results['archive_submission_race'] = {'job_status': 'queued', 'source_still_in_ready': source.exists(), 'source_moved_to_archive': (service.settings.directories.archive / source.name).exists()}
    bridge.close()

# No real operations: reproduce protocol serialization failure and control starvation.
fake = MagicMock()
fake.handle.return_value = {'not_serializable': {1, 2}}
output = io.StringIO()
serve(fake, io.StringIO('{"id":1,"method":"test"}\n'), output)
results['serialization_failure'] = {'response_count': len(output.getvalue().splitlines())}
started, release, cancelled = Barrier(5), Event(), Event()
def blocking_handle(method, params):
    if method == 'slow':
        started.wait(timeout=5)
        release.wait(5)
    else:
        cancelled.set()
    return {}
def requests():
    for request_id in range(4):
        yield json.dumps({'id': request_id, 'method': 'slow'}) + '\n'
    started.wait(timeout=5)
    yield '{"id":5,"method":"jobs.cancel"}\n'
    results['control_starvation'] = {'cancel_served_while_four_requests_blocked': cancelled.wait(.2)}
    release.set()
fake = MagicMock()
fake.handle.side_effect = blocking_handle
serve(fake, requests(), io.StringIO())
print(json.dumps(results, indent=2))
