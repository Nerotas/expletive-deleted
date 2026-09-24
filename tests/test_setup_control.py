"""Offline protocol saturation, strict serialization, and approval ownership."""
import io
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from time import monotonic
from types import SimpleNamespace
from unittest.mock import MagicMock

from backend.desktop.installation import InstallationController, SetupBusyError
from backend.desktop.protocol import serve


class SetupControlTests(unittest.TestCase):
    def test_malformed_request_does_not_end_the_protocol(self):
        bridge = MagicMock()
        bridge.handle.return_value = {'alive': True}
        output = io.StringIO()
        serve(bridge, io.StringIO('{"id":1,"method":[]}\n{"id":2,"method":"dependencies.active"}\n'), output)
        values = {value['id']: value for value in map(json.loads, output.getvalue().splitlines())}
        self.assertFalse(values[1]['ok'])
        self.assertEqual(values[2]['result'], {'alive': True})

    def test_saturated_workers_do_not_delay_status_cancel_or_active_lookup(self):
        release = Event()
        entered = Event()
        guard = Lock()
        count = 0
        bridge = MagicMock()

        def handle(method, params):
            nonlocal count
            if method == 'slow':
                with guard:
                    count += 1
                    if count == 4:
                        entered.set()
                self.assertTrue(release.wait(5))
                return None
            self.assertTrue(entered.wait(3))
            if method == 'dependencies.cancel':
                release.set()
            return {'responsive': True}

        bridge.handle.side_effect = handle
        methods = ['slow'] * 4 + ['dependencies.status', 'dependencies.active', 'dependencies.cancel']
        output = io.StringIO()
        start = monotonic()
        try:
            serve(bridge, io.StringIO(''.join(json.dumps({'id': index, 'method': method}) + '\n' for index, method in enumerate(methods, 1))), output)
        finally:
            release.set()
        self.assertLess(monotonic() - start, 2)
        responses = {value['id']: value for value in map(json.loads, output.getvalue().splitlines())}
        for key in (5, 6, 7):
            self.assertEqual(responses[key]['result'], {'responsive': True})

    def test_non_json_results_and_broken_error_details_get_correlated_errors(self):
        for value in (float('nan'), object()):
            bridge = MagicMock()
            bridge.handle.return_value = value
            output = io.StringIO()
            serve(bridge, io.StringIO('{"id":9,"method":"test"}\n'), output)
            result = json.loads(output.getvalue())
            self.assertEqual(result['id'], 9)
            self.assertFalse(result['ok'])
            self.assertEqual(result['error']['code'], 'protocol_error')
        error = RuntimeError('failure')
        error.diagnostic = object()
        bridge.handle.side_effect = error
        output = io.StringIO()
        serve(bridge, io.StringIO('{"id":10,"method":"test"}\n'), output)
        self.assertEqual(json.loads(output.getvalue())['error']['code'], 'protocol_error')

    def test_lost_start_ack_lookup_and_concurrent_approval_schedule_one_worker(self):
        controller = InstallationController(MagicMock())
        controller._install_executor.shutdown()
        controller._install_executor = MagicMock()
        controller._install_plans['reviewed'] = SimpleNamespace(actions=[SimpleNamespace(component='model')])
        controller._plan_contexts['reviewed'] = SimpleNamespace(cache_dir=None)
        with ThreadPoolExecutor(max_workers=8) as pool:
            replies = list(pool.map(lambda _: controller.handle('dependencies.install', {'plan_id': 'reviewed'}), range(16)))
        controller._install_executor.submit.assert_called_once()
        self.assertEqual(len({reply['install_id'] for reply in replies}), 1)
        active = controller.handle('dependencies.active', {'plan_id': 'reviewed'})
        self.assertEqual(active['install_id'], replies[0]['install_id'])
        controller._install_plans['different'] = controller._install_plans['reviewed']
        with self.assertRaises(SetupBusyError) as raised:
            controller.handle('dependencies.install', {'plan_id': 'different'})
        self.assertEqual(raised.exception.code, 'setup_busy')
        controller.handle('dependencies.cancel', {'install_id': active['install_id']})
        self.assertEqual(controller.handle('dependencies.active', {'plan_id': 'reviewed'})['status'], 'canceling')
        controller._install_jobs[active['install_id']]['status'] = 'completed'
        self.assertEqual(controller.handle('dependencies.active', {'plan_id': 'reviewed'})['status'], 'completed')
        self.assertEqual(controller.handle('dependencies.install', {'plan_id': 'reviewed'})['status'], 'completed')
        controller._install_executor.submit.assert_called_once()
        self.assertIsNone(controller.handle('dependencies.active', {'plan_id': 'unknown'}))


if __name__ == '__main__':
    unittest.main()
