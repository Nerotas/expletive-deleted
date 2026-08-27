import io
import json
import tempfile
import unittest
from pathlib import Path
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

    def test_review_list_reads_a_saved_transcript_and_excludes_classified_words(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "movie.mkv"
            transcript = root / "movie-transcript.json"
            transcript.write_text(
                json.dumps({"words": [{"word": "weirdo", "start": 3.0, "end": 3.4}]}),
                encoding="utf-8",
            )
            service = MagicMock()
            service.settings.directories.transcripts = root
            bridge = DesktopBridge(service)

            with (
                patch("scripts.desktop_bridge.get_profanity_censor_words_file", return_value=root / "words.txt"),
                patch("scripts.desktop_bridge.get_profanity_exclusions_file", return_value=root / "exclusions.txt"),
                patch("scripts.desktop_bridge.load_profanity_censor_words", return_value={"fuck"}),
                patch("scripts.desktop_bridge.load_profanity_exclusions", return_value=set()),
            ):
                result = bridge.handle("reviews.list", {"source": str(source)})

        self.assertEqual(result["candidates"], [{"word": "weirdo", "start": 3.0, "end": 3.4}])

    def test_dictionary_inventory_includes_unique_unclassified_discovered_words(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "one-transcript.json").write_text(
                json.dumps({"words": [{"word": "weirdo"}, {"word": "jerk"}]}),
                encoding="utf-8",
            )
            (root / "two-transcript.json").write_text(
                json.dumps({"words": [{"word": "weirdo"}]}),
                encoding="utf-8",
            )
            service = MagicMock()
            service.settings.directories.transcripts = root
            bridge = DesktopBridge(service)

            with (
                patch("scripts.desktop_bridge.get_profanity_censor_words_file", return_value=root / "words.txt"),
                patch("scripts.desktop_bridge.get_profanity_exclusions_file", return_value=root / "exclusions.txt"),
                patch("scripts.desktop_bridge.load_profanity_censor_words", return_value={"jerk"}),
                patch("scripts.desktop_bridge.load_profanity_exclusions", return_value=set()),
                patch(
                    "scripts.desktop_bridge.find_review_candidates",
                    side_effect=lambda payload, censor, _exclude: [
                        {"word": item["word"]}
                        for item in payload["words"]
                        if item["word"] not in censor
                    ],
                ),
            ):
                result = bridge.handle("dictionary.get")

        self.assertEqual(result["discovered_count"], 1)
        self.assertEqual(result["discovered"], ["weirdo"])

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
