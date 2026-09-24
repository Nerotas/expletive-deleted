"""Native state-smoke fixture: real bridge/store, offline component verification only."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import os
import time
from types import SimpleNamespace
from backend.desktop import installation
from backend.desktop.bridge import DesktopBridge
from backend.desktop.protocol import main, serve
from backend.runtime.dependency_models import InstallResult, InstallProgress
from backend.service import BackendService
from backend.settings import AppSettings, SettingsStore

root = Path(os.environ['CENSOR_APP_DATA_DIR']).parent


def barrier(name):
    (root / f'{name}.started').write_text('ready')
    deadline = time.monotonic() + 45
    while not (root / f'{name}.release').exists():
        if time.monotonic() > deadline:
            raise RuntimeError(f'Native smoke did not release {name}')
        time.sleep(.02)


def execute(plan, *, cache_dir, progress_callback, **kwargs):
    count = root / 'install-count.txt'
    count.write_text(str(int(count.read_text()) + 1 if count.exists() else 1))
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / 'completed-download.fixture').write_bytes(b'completed synthetic download')
    barrier('install')
    for action in plan.actions:
        progress_callback(InstallProgress(action.id, 'completed', 'Verified fixture'))
    return tuple(InstallResult(action.id, action.dependency_ids, 'offline fixture') for action in plan.actions)


def inspect_ytdlp(selected):
    barrier('inspection')
    return SimpleNamespace(ready=True, path=Path(selected), detail='offline fixture')


installation.execute_install_plan = execute
installation.inspect_whisper_model = lambda *args, **kwargs: SimpleNamespace(ready=True, detail='offline fixture')
installation.inspect_ytdlp = inspect_ytdlp
service = BackendService(SettingsStore(defaults=AppSettings.defaults(root / 'media')))
service.get_capabilities = lambda: {
    'ready': False, 'processing_ready': False, 'app_runtime': 'ready',
    'ffmpeg': True, 'ffprobe': True, 'whisper': True, 'whisper_library': 'faster-whisper',
    'whisper_model': 'large-v3', 'whisper_model_ready': False, 'whisper_device': 'cpu',
    'video_encoders': [], 'ytdlp': True, 'js_runtime': True,
}
sys.stdin.reconfigure(encoding='utf-8')
sys.stdout.reconfigure(encoding='utf-8')
protocol_output = sys.stdout
sys.stdout = sys.stderr
raise SystemExit(serve(DesktopBridge(service), output_stream=protocol_output))
