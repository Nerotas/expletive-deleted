import io
import json
import unittest
from unittest.mock import MagicMock, patch

from scripts.desktop_bridge import DesktopBridge, serve


class DesktopBridgeTests(unittest.TestCase):
    def test_dictionary_inventory_reports_backend_policy_counts(self):
        service = MagicMock()
        bridge = DesktopBridge(service)

        with (
            patch("scripts.desktop_bridge.get_profanity_censor_words_file", return_value="words.txt"),
            patch("scripts.desktop_bridge.get_profanity_exclusions_file", return_value="exclusions.txt"),
            patch("scripts.desktop_bridge.load_profanity_censor_words", return_value={"one", "two"}),
            patch("scripts.desktop_bridge.load_profanity_exclusions", return_value={"allowed"}),
        ):
            result = bridge.handle("dictionary.get")

        self.assertEqual(result["words_count"], 2)
        self.assertEqual(result["exclusions_count"], 1)

    def test_protocol_returns_library_and_correlates_request(self):
        service = MagicMock()
        item = MagicMock()
        item.to_dict.return_value = {"source": "C:/media/movie.mkv", "status": "ready"}
        service.get_library.return_value = (item,)
        request = io.StringIO('{"id":7,"method":"library.list"}\n')
        output = io.StringIO()

        exit_code = serve(DesktopBridge(service), request, output)

        response = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(response["id"], 7)
        self.assertTrue(response["ok"])
        self.assertEqual(response["result"][0]["status"], "ready")
        service.close.assert_called_once()

    def test_protocol_returns_structured_error(self):
        service = MagicMock()
        request = io.StringIO('{"id":8,"method":"not.real"}\n')
        output = io.StringIO()

        serve(DesktopBridge(service), request, output)

        response = json.loads(output.getvalue())
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["type"], "ValueError")
        self.assertIn("Unknown desktop bridge method", response["error"]["message"])


if __name__ == "__main__":
    unittest.main()