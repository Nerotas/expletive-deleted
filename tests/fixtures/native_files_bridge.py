"""Offline native tests use real file guards and substitute only media verification."""
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.environ['NATIVE_FILES_TEST_REPO'])
from backend.desktop.bridge import DesktopBridge
from backend.desktop.protocol import serve
from backend.process_lifetime import contain_process_tree
from backend.service import BackendService
from backend.settings import AppSettings, DirectorySettings, SettingsStore

root = Path(os.environ['NATIVE_FILES_TEST_ROOT'])
settings = AppSettings(directories=DirectorySettings(*(root / name for name in ['Ready', 'Finished', 'Processed', 'Transcripts'])))


def verify(path, _ffprobe):
    if path.read_bytes() != b'synthetic verified output':
        raise ValueError('Synthetic verifier rejected output')


if __name__ == '__main__':
    contain_process_tree()
    sys.stdin.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')
    output = sys.stdout
    sys.stdout = sys.stderr
    with patch('backend.service.outputs.verify_playback', verify):
        serve(DesktopBridge(BackendService(SettingsStore(root / 'settings.ini', settings))), output_stream=output)
