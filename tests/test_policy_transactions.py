"""Real contention and crash recovery; all fixture dictionary content is synthetic."""

import json
import multiprocessing
import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from backend.filesystem.locking import StoreBusyError, store_lock
from backend.policy import PolicyFileError, PolicyStore
from backend.policy.errors import PolicyRecoveryError
from backend.policy import transactions


def make_store(root, **kwargs):
    root = Path(root)
    return PolicyStore(root / "dictionary", censor_defaults_path=root / "censor.txt",
                       exclusions_defaults_path=root / "exclude.txt", **kwargs)


def race_worker(root, barrier, prefix):
    store = make_store(root)
    barrier.wait(15)
    for index in range(6):
        store.update("censor", f"{prefix}-{index}", "add")
        store.update("exclude", f"{prefix}-{index}", "add")
        store.update("censor", f"remove-{prefix}-{index}", "remove")
        store.add_discovered({f"candidate-{prefix}-{index}", f"{prefix}-{index}"})


def lock_worker(root, ready, release):
    with store_lock(Path(root) / "dictionary" / transactions.LOCK_NAME):
        ready.set()
        release.wait(30)


def crash_worker(root, boundary, operation):
    store = make_store(root)
    original = transactions.write_atomic
    publications = 0

    def publish(path, payload):
        nonlocal publications
        if boundary == 0:
            os._exit(71)
        original(path, payload)
        publications += 1
        if publications == boundary:
            os._exit(71)

    unlink = Path.unlink

    def cleanup(path, *args, **kwargs):
        if path.name == transactions.JOURNAL_NAME and boundary == 5:
            os._exit(71)
        result = unlink(path, *args, **kwargs)
        if path.name == transactions.JOURNAL_NAME and boundary == 6:
            os._exit(71)
        return result

    with patch.object(transactions, "write_atomic", publish), patch.object(Path, "unlink", cleanup), \
            patch.object(PolicyStore, "_timestamp", return_value="2026-09-23T00:00:00Z"):
        if operation == "update":
            store.update("exclude", "candidate", "add")
        elif operation == "import":
            store.import_dictionary(Path(root) / "import.json")
        elif operation == "restore":
            store.restore_defaults()
        else:
            store.add_discovered({"candidate"})


class PolicyTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "censor.txt").write_text("seed\n", encoding="utf-8")
        (self.root / "exclude.txt").write_text("allowed\n", encoding="utf-8")
        self.store = make_store(self.root)
        self.context = multiprocessing.get_context("spawn")

    def run_process(self, target, *args):
        process = self.context.Process(target=target, args=args)
        process.start()
        self.addCleanup(lambda: self.stop_process(process))
        return process

    @staticmethod
    def stop_process(process):
        if process.is_alive():
            process.terminate()
        process.join(10)

    def assert_consistent(self, policy):
        self.assertFalse(policy.censor_words & policy.exclusions)
        self.assertFalse(set(self.store.load_discovered()) & (policy.censor_words | policy.exclusions))

    def test_barrier_controlled_threads_and_separate_stores_preserve_edits(self):
        for separate in (False, True):
            with self.subTest(separate=separate):
                barrier = threading.Barrier(3)
                stores = [make_store(self.root) if separate else self.store for _ in range(2)]

                def edit(index):
                    barrier.wait(10)
                    word = f"thread-{str(separate).lower()}-{index}"
                    stores[index].update("censor", word, "add")
                    stores[index].add_discovered({f"discovered-{word}"})
                    return word

                with ThreadPoolExecutor(2) as executor:
                    futures = [executor.submit(edit, index) for index in range(2)]
                    barrier.wait(10)
                    acknowledged = {future.result(15) for future in futures}
                self.assertTrue(acknowledged <= self.store.load().censor_words)
                self.assertTrue({f"discovered-{word}" for word in acknowledged} <= set(self.store.load_discovered()))

    def test_independent_process_races_add_remove_classify_and_discover(self):
        for prefix in ("a", "b"):
            for index in range(6):
                self.store.update("censor", f"remove-{prefix}-{index}", "add")
        barrier = self.context.Barrier(3)
        children = [self.run_process(race_worker, str(self.root), barrier, prefix) for prefix in ("a", "b")]
        barrier.wait(15)
        for child in children:
            child.join(30)
            self.assertEqual(child.exitcode, 0)
        policy = self.store.load()
        for prefix in ("a", "b"):
            for index in range(6):
                self.assertIn(f"{prefix}-{index}", policy.exclusions)
                self.assertNotIn(f"remove-{prefix}-{index}", policy.censor_words)
                self.assertIn(f"candidate-{prefix}-{index}", self.store.load_discovered())
        self.assert_consistent(policy)

    def test_import_restore_discovery_and_export_snapshots_are_serialized(self):
        source = self.store.export_dictionary(self.root / "import.json")
        for replace in (lambda: self.store.import_dictionary(source), self.store.restore_defaults):
            entered = threading.Event()
            release = threading.Event()
            contender = threading.Event()
            original = self.store._write_dictionary

            def paused(*args, **kwargs):
                original(*args, **kwargs)
                entered.set()
                self.assertTrue(release.wait(10))

            def edit():
                contender.set()
                store = make_store(self.root)
                store.update("exclude", "seed", "add")
                store.add_discovered({"seed", "new-candidate"})
                return store.export_payload()

            with patch.object(self.store, "_write_dictionary", paused), ThreadPoolExecutor(2) as executor:
                replacing = executor.submit(replace)
                self.assertTrue(entered.wait(10))
                editing = executor.submit(edit)
                self.assertTrue(contender.wait(10))
                self.assertFalse(editing.done())
                release.set()
                self.assertFalse(replacing.result(15).censor_words & replacing.result().exclusions)
                exported = editing.result(15)
            self.assertIn("seed", {entry["value"] for entry in exported["exclusions"]})
            self.assertNotIn("seed", {entry["value"] for entry in exported["words"]})
            self.assert_consistent(self.store.load())

    def test_crash_at_every_publication_boundary_recovers_metadata(self):
        for operation in ("update", "import", "restore", "initialize"):
            for boundary in range(7):
                with self.subTest(operation=operation, boundary=boundary), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    (root / "censor.txt").write_text("seed\n", encoding="utf-8")
                    (root / "exclude.txt").write_text("allowed\n", encoding="utf-8")
                    store = make_store(root)
                    if operation != "initialize":
                        store.add_discovered({"candidate"})
                        store.update("censor", "untouched", "add")
                        before = store.export_payload()
                        store.export_dictionary(root / "import.json")
                    child = self.run_process(crash_worker, str(root), boundary, operation)
                    child.join(20)
                    self.assertEqual(child.exitcode, 71)
                    # Targeted reads must also finish pending multi-store recovery.
                    reopened = make_store(root)
                    reopened.load_entries("exclude")
                    policy = reopened.load()
                    self.assertFalse(policy.censor_words & policy.exclusions)
                    self.assertFalse(set(reopened.load_discovered()) & (policy.censor_words | policy.exclusions))
                    self.assertFalse((store.directory / transactions.JOURNAL_NAME).exists())
                    if operation == "update" and boundary:
                        self.assertEqual(policy.exclusion_entries["candidate"].added_at, "2026-09-23T00:00:00Z")
                        self.assertEqual(policy.exclusion_entries["candidate"].source, "user")
                        self.assertEqual(reopened.export_payload()["words"], before["words"])
                    elif operation == "import" and boundary:
                        self.assertTrue(all(entry.source == "imported" and entry.added_at == "2026-09-23T00:00:00Z" for entry in policy.entries("censor")))
                    elif operation == "restore" and boundary:
                        self.assertEqual(policy.censor_words, {"seed"})
                        self.assertEqual(policy.censor_entries["seed"].source, "default")
                    elif operation != "initialize":
                        self.assertEqual(reopened.export_payload(), before)

    def test_corrupt_journals_never_seed_or_modify_existing_data(self):
        self.store.load()
        before = self.store.censor_path.read_bytes()
        self.store.exclusions_path.unlink()
        sentinel = self.root / "outside.json"
        sentinel.write_text("sentinel", encoding="utf-8")
        valid = {"version": 1, "transaction_id": str(uuid4()), "stores": {"../outside.json": {}}}
        for content in (b"{", b"\xff", b'{"version":1,"version":1}', json.dumps(valid).encode(),
                        json.dumps({**valid, "stores": {"censored.json": {}}}).encode()):
            journal = self.store.directory / transactions.JOURNAL_NAME
            journal.write_bytes(content)
            for operation in (self.store.load, self.store.info, self.store.restore_defaults,
                              self.store.initialize_discovered, lambda: self.store.load_entries("exclude")):
                with self.assertRaises(PolicyRecoveryError):
                    operation()
            self.assertEqual(self.store.censor_path.read_bytes(), before)
            self.assertFalse(self.store.exclusions_path.exists())
            self.assertEqual(journal.read_bytes(), content)
            self.assertEqual(sentinel.read_text(), "sentinel")

    def test_lock_timeout_owner_death_and_reentrancy(self):
        ready, release = self.context.Event(), self.context.Event()
        owner = self.run_process(lock_worker, str(self.root), ready, release)
        self.assertTrue(ready.wait(15))
        with self.assertRaisesRegex(StoreBusyError, "retry"):
            make_store(self.root, lock_timeout=0.05).load()
        owner.terminate()
        owner.join(10)
        # No stale PID removal or lock-file deletion is needed after owner death.
        with store_lock(self.store.directory / transactions.LOCK_NAME):
            with store_lock(self.store.directory / transactions.LOCK_NAME):
                self.store.update("censor", "after-death", "add")
        self.assertIn("after-death", self.store.load().censor_words)

    def test_thread_lock_timeout_is_actionable(self):
        with store_lock(self.store.directory / transactions.LOCK_NAME), ThreadPoolExecutor(1) as executor:
            future = executor.submit(make_store(self.root, lock_timeout=0.01).load)
            with self.assertRaises(StoreBusyError):
                future.result(5)

    def test_export_cannot_overwrite_managed_store(self):
        self.store.load()
        for name in transactions.STORE_NAMES | {transactions.JOURNAL_NAME, transactions.LOCK_NAME}:
            with self.assertRaises(PolicyFileError):
                self.store.export_dictionary(self.store.directory / name)
        if os.name == "nt":
            with self.assertRaises(PolicyFileError):
                self.store.export_dictionary(self.store.directory / "CENSORED.JSON")

    def test_readers_wait_for_complete_publication_and_recovery_io_is_retryable(self):
        self.store.add_discovered({"candidate"})
        published = threading.Event()
        release = threading.Event()
        entered = threading.Event()
        original = transactions.write_atomic

        def interrupt(path, payload):
            original(path, payload)
            if path.name == "censored.json":
                published.set()
                self.assertTrue(release.wait(10))
                raise OSError("synthetic disk error")

        def snapshot():
            entered.set()
            return make_store(self.root).load()

        with patch.object(transactions, "write_atomic", interrupt), ThreadPoolExecutor(2) as executor:
            writer = executor.submit(self.store.update, "exclude", "candidate", "add")
            self.assertTrue(published.wait(10))
            reader = executor.submit(snapshot)
            self.assertTrue(entered.wait(10))
            self.assertFalse(reader.done())
            release.set()
            with self.assertRaises(PolicyRecoveryError):
                writer.result(15)
            with self.assertRaises(PolicyRecoveryError):
                reader.result(15)
        pending = self.store.directory / transactions.JOURNAL_NAME
        self.assertTrue(pending.exists())
        recovered = make_store(self.root).load()
        self.assertIn("candidate", recovered.exclusions)
        self.assert_consistent(recovered)
        self.assertFalse(pending.exists())

    def test_journal_validates_all_payloads_and_classifications_before_writing(self):
        self.store.load()
        original = {name: (self.store.directory / name).read_bytes()
                    for name in ("censored.json", "exclusions.json")}
        censor = json.loads(original["censored.json"])
        exclude = json.loads(original["exclusions.json"])
        contradictory = {**exclude, "entries": censor["entries"]}
        for payloads in ({"censored.json": censor, "exclusions.json": {}},
                         {"censored.json": censor, "exclusions.json": contradictory},
                         {"censored.json": censor, "discovered.json": {"schema_version": 1, "words": ["seed"]}}):
            journal = self.store.directory / transactions.JOURNAL_NAME
            journal.write_text(json.dumps({"version": 1, "transaction_id": str(uuid4()), "stores": payloads}), encoding="utf-8")
            with self.assertRaises(PolicyRecoveryError):
                self.store.export_payload()
            for name, content in original.items():
                self.assertEqual((self.store.directory / name).read_bytes(), content)


if __name__ == "__main__":
    unittest.main()
