"""Offline native recovery fixture; production dispatch/ownership stay intact."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import json
import os
import time
from threading import Lock
from types import SimpleNamespace
from backend.desktop import installation
from backend.desktop.bridge import DesktopBridge
from backend.desktop.protocol import serve
from backend.runtime.dependency_models import InstallResult, InstallProgress
from backend.service import BackendService
from backend.settings import AppSettings, SettingsStore

root = Path(os.environ['CENSOR_APP_DATA_DIR']).parent
guard = Lock()


def mode():
    try:
        return (root / 'mode').read_text()
    except FileNotFoundError:
        return ''


def execute(plan, *, cache_dir, progress_callback, cancellation, **kwargs):
    count = root / 'install-count.txt'
    count.write_text(str(int(count.read_text()) + 1 if count.exists() else 1))
    cache_dir.mkdir(parents=True, exist_ok=True)
    completed = cache_dir / 'completed-download.fixture'
    if not completed.exists():
        completed.write_bytes(b'completed synthetic download')
    (root / 'install.started').write_text('ready')
    deadline = time.monotonic() + 150
    while not (root / 'install.release').exists():
        if cancellation.is_set():
            (root / 'cancel.received').write_text('flag set')
        if time.monotonic() > deadline:
            raise RuntimeError('Smoke did not release setup')
        time.sleep(.02)
    if cancellation.is_set():
        raise RuntimeError('Cancelled after retaining completed files')
    for action in plan.actions:
        progress_callback(InstallProgress(action.id, 'completed', 'Verified fixture'))
    return tuple(InstallResult(action.id, action.dependency_ids, 'offline fixture') for action in plan.actions)


installation.execute_install_plan = execute
installation.inspect_whisper_model = lambda *args, **kwargs: SimpleNamespace(ready=True, detail='offline fixture')
service = BackendService(SettingsStore(defaults=AppSettings.defaults(root / 'media')))


def capabilities():
    if (root / 'saturate').exists():
        with guard:
            with (root / 'saturated.jsonl').open('a') as stream:
                stream.write('entered\n')
        deadline = time.monotonic() + 30
        while (root / 'saturate').exists() and time.monotonic() < deadline:
            time.sleep(.01)
    return {
        'ready': False, 'processing_ready': False, 'app_runtime': 'ready',
        'ffmpeg': True, 'ffprobe': True, 'whisper': True, 'whisper_library': 'faster-whisper',
        'whisper_model': 'large-v3', 'whisper_model_ready': False, 'whisper_device': 'cpu',
        'video_encoders': [], 'ytdlp': True, 'js_runtime': True,
    }


service.get_capabilities = capabilities
sys.stdin.reconfigure(encoding='utf-8')
sys.stdout.reconfigure(encoding='utf-8')
output = sys.stdout
sys.stdout = sys.stderr


class FilterOutput:
    def write(self, text):
        value = json.loads(text)
        result = value.get('result')
        if isinstance(result, dict) and 'install_id' in result:
            current = mode()
            if current == 'start':
                (root / 'mode').write_text('')
                return
            if current == 'silence':
                return
        output.write(text)

    def flush(self):
        output.flush()


raise SystemExit(serve(DesktopBridge(service), output_stream=FilterOutput()))
