import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.issue83_contract import ContractError, validate_input_lock, validate_inventory, validate_trees


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class Issue83ContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.installer = self.root / "installer"
        self.source = self.root / "source"
        self.installer.mkdir()
        self.source.mkdir()
        self.contents = {
            ("installer", "bin/tool.exe"): b"tool-binary",
            ("installer", "LICENSES/demo.txt"): b"license-text",
            ("installer", "NOTICES/demo.txt"): b"notice-text",
            ("source", "sources/demo.tar.gz"): b"source-archive",
        }
        artifacts = []
        files = []
        for (scope, path), content in self.contents.items():
            kind = "payload" if path.endswith(".exe") else "source" if scope == "source" else "license" if path.startswith("LICENSES/") else "notice"
            artifact_id = f"demo-{kind}"
            artifacts.append({
                "id": artifact_id,
                "kind": kind,
                "name": Path(path).name,
                "url": f"https://example.org/{Path(path).name}",
                "sha256": digest(content),
            })
            files.append({
                "scope": scope,
                "path": path,
                "sha256": digest(content),
                "purpose": kind,
                "owner_component_id": "demo",
                "transformation_id": f"copy-{kind}",
                "derived_from": [artifact_id],
            })
            destination = (self.installer if scope == "installer" else self.source) / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        self.lock = {
            "schema_version": 1,
            "status": "approved",
            "release_id": "fixture-1",
            "platform": "win32-x64",
            "components": [{
                "id": "demo",
                "version": "1.0",
                "license_expression": "MIT",
                "artifacts": artifacts,
                "source_artifact_ids": ["demo-source"],
                "notice_artifact_ids": ["demo-notice"],
                "license_artifact_ids": ["demo-license"],
            }],
            "transformations": [
                {"id": f"copy-{kind}", "kind": "copy", "input_artifact_ids": [f"demo-{kind}"]}
                for kind in ("payload", "license", "notice", "source")
            ],
        }
        self.lock_bytes = json.dumps(self.lock, sort_keys=True).encode("utf-8")
        self.inventory = {
            "schema_version": 1,
            "release_id": "fixture-1",
            "platform": "win32-x64",
            "input_lock_sha256": digest(self.lock_bytes),
            "files": files,
        }

    def test_valid_fixture_passes_both_contracts(self):
        validate_inventory(self.lock, self.lock_bytes, self.inventory)
        validate_trees(self.inventory, self.installer, self.source)

    def test_candidate_lock_is_rejected(self):
        self.lock["status"] = "candidate"
        with self.assertRaisesRegex(ContractError, "approved"):
            validate_input_lock(self.lock)

    def test_embedded_notice_must_identify_its_hashed_archive(self):
        artifacts = self.lock["components"][0]["artifacts"]
        payload = next(item for item in artifacts if item["kind"] == "payload")
        notice = next(item for item in artifacts if item["kind"] == "notice")
        notice["url"] = payload["url"]
        notice["origin_artifact_id"] = payload["id"]
        notice["archive_member"] = "THIRD_PARTY_NOTICES.txt"
        validate_input_lock(self.lock)
        notice["url"] = "https://example.org/other.zip"
        with self.assertRaisesRegex(ContractError, "same-component archive origin"):
            validate_input_lock(self.lock)

    def test_missing_notice_fails_closed(self):
        self.inventory["files"] = [item for item in self.inventory["files"] if item["purpose"] != "notice"]
        with self.assertRaisesRegex(ContractError, "notice_artifact_ids"):
            validate_inventory(self.lock, self.lock_bytes, self.inventory)

    def test_missing_source_mapping_fails_closed(self):
        self.inventory["files"] = [item for item in self.inventory["files"] if item["purpose"] != "source"]
        with self.assertRaisesRegex(ContractError, "source_artifact_ids"):
            validate_inventory(self.lock, self.lock_bytes, self.inventory)

    def test_missing_payload_fails_closed(self):
        self.inventory["files"] = [item for item in self.inventory["files"] if item["purpose"] != "payload"]
        with self.assertRaisesRegex(ContractError, "payload is absent"):
            validate_inventory(self.lock, self.lock_bytes, self.inventory)

    def test_extra_binary_fails_closed(self):
        (self.installer / "bin" / "extra.dll").write_bytes(b"unreviewed")
        with self.assertRaisesRegex(ContractError, "undeclared file"):
            validate_trees(self.inventory, self.installer, self.source)

    def test_tampered_file_fails_closed(self):
        (self.installer / "bin" / "tool.exe").write_bytes(b"tampered")
        with self.assertRaisesRegex(ContractError, "hash mismatch"):
            validate_trees(self.inventory, self.installer, self.source)

    def test_path_escape_fails_closed(self):
        self.inventory["files"][0]["path"] = "../escape.exe"
        with self.assertRaisesRegex(ContractError, "safe relative"):
            validate_inventory(self.lock, self.lock_bytes, self.inventory)

    def test_windows_device_path_fails_closed(self):
        self.inventory["files"][0]["path"] = "bin/CON.exe"
        with self.assertRaisesRegex(ContractError, "safe relative"):
            validate_inventory(self.lock, self.lock_bytes, self.inventory)

    def test_case_colliding_inventory_path_fails_closed(self):
        duplicate = copy.deepcopy(self.inventory["files"][0])
        duplicate["path"] = duplicate["path"].upper()
        self.inventory["files"].append(duplicate)
        with self.assertRaisesRegex(ContractError, "duplicate inventory path"):
            validate_inventory(self.lock, self.lock_bytes, self.inventory)

    def test_unknown_transformation_fails_closed(self):
        self.inventory["files"][0]["transformation_id"] = "unknown"
        with self.assertRaisesRegex(ContractError, "unknown transformation"):
            validate_inventory(self.lock, self.lock_bytes, self.inventory)

    def test_copy_hash_must_match_input_lock(self):
        altered = copy.deepcopy(self.inventory)
        altered["files"][0]["sha256"] = digest(b"different")
        with self.assertRaisesRegex(ContractError, "copied artifact hash"):
            validate_inventory(self.lock, self.lock_bytes, altered)


if __name__ == "__main__":
    unittest.main()
