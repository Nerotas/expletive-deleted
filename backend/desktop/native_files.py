"""Main-process-only file transactions; tokens never cross the renderer boundary."""

import json
from contextlib import ExitStack
from pathlib import Path
from threading import RLock, Timer
from uuid import uuid4

from backend.filesystem.operations import locked_file
from backend.filesystem.paths import RootBinding, validate_path, version
from backend.filesystem.publication import Publication
from backend.service.outputs import prepare_output
from .dictionary import DictionaryController


class NativeFileError(ValueError):
    code = 'native_file_rejected'


class NativeFiles:
    def __init__(self, service, policy_store, *, lease_seconds=30):
        self.service, self.policy_store = service, policy_store
        self.lease_seconds = lease_seconds
        self._lock, self._leases, self._closed = RLock(), {}, False

    def _remember(self, resources, **data):
        token = uuid4().hex
        timer = Timer(self.lease_seconds, self.release, args=(token,))
        timer.daemon = True
        self._leases[token] = dict(data, resources=resources, timer=timer)
        timer.start()
        return token

    def release(self, token):
        with self._lock:
            lease = self._leases.pop(token, None)
            if lease:
                lease['timer'].cancel()
                lease['resources'].close()

    def close(self):
        with self._lock:
            self._closed = True
            self.release_all()

    def release_all(self):
        with self._lock:
            for token in list(self._leases):
                self.release(token)

    @staticmethod
    def _json_path(value):
        if not isinstance(value, str) or not value.strip():
            raise NativeFileError('Choose a dictionary JSON file.')
        path = validate_path(Path(value))
        if path.suffix.lower() != '.json' or path.is_symlink() or path.is_dir():
            raise NativeFileError('Choose an ordinary .json dictionary file.')
        return path

    def handle(self, method, params):
        with self._lock:
            if self._closed:
                raise NativeFileError('The desktop application is closing.')
            if method == 'native.release_all':
                self.release_all()
                return None
            if method == 'native.release':
                self.release(params.get('token'))
                return None
            if method in ('native.output.prepare', 'native.export.prepare'):
                resources = ExitStack()
                try:
                    if method == 'native.output.prepare':
                        path, check = prepare_output(self.service, params.get('source'), resources)
                        token = self._remember(resources, kind='output', path=path, check=check)
                        return {'token': token}
                    path = self._json_path(params.get('destination'))
                    root = RootBinding.capture(path.parent)
                    path = resources.enter_context(root.lease(path))
                    expected = None
                    if path.exists():
                        with locked_file(root, path):
                            expected = version(path)
                    token = self._remember(resources, kind='export', path=path, root=root, expected=expected)
                    return {'token': token, 'exists': expected is not None}
                except BaseException:
                    resources.close()
                    raise
            if method == 'native.dictionary.import':
                path = self._json_path(params.get('source'))
                with locked_file(RootBinding.capture(path.parent), path):
                    policy = self.policy_store.import_dictionary(path)
                return DictionaryController._dictionary_result(policy)
            token = params.get('token')
            lease = self._leases.get(token)
            if not lease:
                raise NativeFileError('This file selection expired. Choose the file again.')
            if method == 'native.output.check' and lease['kind'] == 'output':
                lease['check']()
                return {'path': str(lease['path'])}
            if method == 'native.dictionary.export' and lease['kind'] == 'export':
                try:
                    if lease['expected'] is not None and params.get('overwrite') is not True:
                        raise NativeFileError('Replacing this dictionary file requires confirmation.')
                    with Publication(lease['root'], lease['path'], overwrite=params.get('overwrite') is True,
                                     expected_version=lease['expected']) as publication:
                        payload = self.policy_store.export_payload()
                        publication.stage.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
                        def verify(path):
                            if json.loads(path.read_text(encoding='utf-8')) != payload:
                                raise NativeFileError('The exported dictionary could not be verified.')
                        publication.publish(verify)
                    return {'path': str(lease['path'])}
                finally:
                    self.release(token)
            raise NativeFileError('Unsupported native file operation.')
