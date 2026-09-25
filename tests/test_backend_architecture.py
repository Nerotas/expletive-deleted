"""Protect first-run imports and the backend's dependency direction."""

import ast
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BackendArchitectureTests(unittest.TestCase):
    def run_isolated(self, code: str, *arguments: str, encoding_warnings: bool = False):
        options = ["-S"]
        if encoding_warnings:
            options += ["-X", "warn_default_encoding", "-W", "error::EncodingWarning"]
        result = subprocess.run(
            [sys.executable, *options, "-c", code, *arguments],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_backend_imports_without_processing_packages(self):
        # -S excludes site-packages, matching the private-Python first-run boundary.
        self.run_isolated("""
import importlib, pkgutil, sys
import backend
for module in pkgutil.walk_packages(backend.__path__, backend.__name__ + '.'):
    importlib.import_module(module.name)
assert not {'ctranslate2', 'faster_whisper', 'better_profanity'} & sys.modules.keys()
""")

    def test_transcript_checks_do_not_load_processing_or_runtime_orchestration(self):
        self.run_isolated("""
import sys
from backend.censor.transcripts import validate_transcript_data
validate_transcript_data({'text': '', 'words': [], 'audio_source': 'full_mix'})
assert 'backend.censor.engine' not in sys.modules
assert 'backend.runtime' not in sys.modules
""")

    def test_backend_does_not_import_entrypoints(self):
        wrappers = {path.stem for path in ROOT.glob('*.py')}
        for path in (ROOT / 'backend').rglob('*.py'):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name.split('.')[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    names = [(node.module or '').split('.')[0]]
                else:
                    continue
                with self.subTest(path=path.relative_to(ROOT), line=node.lineno):
                    self.assertFalse(set(names) & (wrappers | {'scripts'}))

    def test_transcript_cache_uses_utf8_under_legacy_encoding(self):
        with tempfile.TemporaryDirectory() as temporary:
            transcript = Path(temporary) / 'transcript.json'
            transcript.write_text(json.dumps({
                'text': '家庭 café', 'words': [], 'audio_source': 'full_mix',
                'whisper_library': 'faster-whisper', 'whisper_model': 'large-v3',
                'source_identity': {'algorithm': 'sha256', 'digest': '0' * 64, 'size_bytes': 0},
            }, ensure_ascii=False), encoding='utf-8')
            # Treat default-encoding use as an error even on a UTF-8 developer host.
            self.run_isolated("""
import sys
from backend.censor import transcripts
transcripts.probe_audio_stream = lambda *args: (2, 'stereo')
assert transcripts.transcript_cache_is_compatible(
    'source.mkv', sys.argv[1], 'unused', 'faster-whisper', 'large-v3')
""", str(transcript), encoding_warnings=True)

    def test_bridge_waits_for_setup_even_when_service_cleanup_fails(self):
        from unittest.mock import MagicMock
        from backend.desktop import DesktopBridge

        service = MagicMock()
        service.close.side_effect = RuntimeError('cleanup failed')
        bridge = DesktopBridge(service, MagicMock())
        bridge.installations._install_executor.shutdown()
        bridge.installations._install_executor = MagicMock()
        with self.assertRaisesRegex(RuntimeError, 'cleanup failed'):
            bridge.close()
        self.assertTrue(bridge.installations._closing)
        bridge.installations._install_executor.shutdown.assert_called_once_with(
            wait=True, cancel_futures=True)
