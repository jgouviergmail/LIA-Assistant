"""Offline tests for the paid-generation checkpoint; no credential or network access."""

import base64
import contextlib
import importlib.util
import io
import json
import tempfile
import threading
import unittest
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "atlas_score", Path(__file__).with_name("generate_atlas_proof_music.py")
)
assert SPEC is not None and SPEC.loader is not None
score = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(score)


class PaidAttemptSafetyTests(unittest.TestCase):
    def setUp(self):
        score.DESTINATION.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="offline-safety-", dir=score.DESTINATION)
        self.addCleanup(temporary.cleanup)
        self.destination = Path(temporary.name)
        override = patch.object(score, "DESTINATION", self.destination)
        override.start()
        self.addCleanup(override.stop)
        score.write_json(
            self.destination / "provider-preflight.json",
            {"requestedModelAvailable": True},
        )

    def twice(self, outcome):
        with (
            contextlib.redirect_stdout(io.StringIO()),
            patch.object(
                score,
                "key_from_existing_configuration",
                return_value="offline-test-key",
            ),
            patch.object(score, "request", side_effect=outcome) as network,
        ):
            score.generate()
            score.generate()
            self.assertEqual(network.call_count, 1)
        return json.loads((self.destination / "generation-attempt.json").read_text())

    def test_completed_attempt_is_never_repeated(self):
        audio = base64.b64encode(b"RIFFoffline-fixture").decode()
        response = {
            "id": "offline-id",
            "steps": [
                {
                    "type": "model_output",
                    "content": [{"type": "audio", "data": audio, "mime_type": "audio/wav"}],
                }
            ],
        }
        record = self.twice([(response, {})])
        self.assertEqual(record["status"], "generated")
        self.assertEqual(record["paidGenerationAttempts"], 1)
        payload = (self.destination / "composition-request.json").read_bytes()
        self.assertFalse(json.loads(payload)["store"])
        self.assertNotIn(b"offline-test-key", payload)

    def test_ambiguous_failure_is_never_repeated(self):
        self.assertEqual(self.twice(TimeoutError())["status"], "outcome_unknown")

    def test_rejected_attempt_is_never_repeated(self):
        error = urllib.error.HTTPError("https://example.invalid", 429, "offline", {}, None)
        self.assertEqual(self.twice(error)["status"], "rejected")

    def test_existing_checkpoint_stops_before_reading_credentials(self):
        score.write_json(self.destination / "generation-attempt.json", {"status": "dispatched"})
        with (
            contextlib.redirect_stdout(io.StringIO()),
            patch.object(score, "key_from_existing_configuration") as key,
        ):
            score.generate()
            key.assert_not_called()

    def test_transient_windows_denial_keeps_old_receipt_until_atomic_replacement(self):
        path = self.destination / "checkpoint.json"
        score.write_json(path, {"status": "old"})
        original_replace = Path.replace
        replace_calls = 0

        def temporarily_blocked(source, destination):
            nonlocal replace_calls
            replace_calls += 1
            if replace_calls == 1:
                self.assertEqual(json.loads(path.read_text()), {"status": "old"})
                error = PermissionError(13, "simulated transient Windows denial")
                error.winerror = 5
                raise error
            return original_replace(source, destination)

        with (
            patch.object(Path, "replace", autospec=True, side_effect=temporarily_blocked),
            patch.object(score.time, "sleep") as wait,
        ):
            score.write_json(path, {"status": "new"})
        self.assertEqual(json.loads(path.read_text()), {"status": "new"})
        self.assertEqual(replace_calls, 2)
        wait.assert_called_once_with(0.02)
        self.assertFalse(path.with_suffix(".json.part").exists())

    def test_permanent_checkpoint_denial_preserves_paid_guard_and_pending_receipt(self):
        error = PermissionError(13, "simulated persistent Windows denial")
        error.winerror = 5
        with (
            contextlib.redirect_stdout(io.StringIO()),
            patch.object(
                score,
                "key_from_existing_configuration",
                return_value="offline-test-key",
            ),
            patch.object(score, "request", return_value=({"status": "completed"}, {})) as network,
            patch.object(Path, "replace", side_effect=error) as replace,
            patch.object(score.time, "sleep") as wait,
        ):
            with self.assertRaises(PermissionError):
                score.generate()
            score.generate()
        self.assertEqual(network.call_count, 1)
        self.assertEqual(replace.call_count, 6)
        self.assertEqual(wait.call_count, 5)
        path = self.destination / "generation-attempt.json"
        self.assertEqual(json.loads(path.read_text())["status"], "dispatched")
        self.assertEqual(
            json.loads(path.with_suffix(".json.part").read_text())["status"], "received"
        )

    def test_unrelated_permission_denial_propagates_without_waiting(self):
        path = self.destination / "checkpoint.json"
        with (
            patch.object(Path, "replace", side_effect=PermissionError(13, "simulated ACL denial")),
            patch.object(score.time, "sleep") as wait,
        ):
            with self.assertRaises(PermissionError):
                score.write_json(path, {"status": "new"})
        wait.assert_not_called()

    def test_concurrent_dispatch_attempts_have_only_one_paid_effect(self):
        barrier = threading.Barrier(2)

        def key():
            barrier.wait(timeout=5)
            return "offline-test-key"

        def dispatch():
            try:
                score.generate()
                return "completed"
            except FileExistsError:
                return "checkpoint_already_claimed"

        with (
            contextlib.redirect_stdout(io.StringIO()),
            patch.object(score, "key_from_existing_configuration", side_effect=key),
            patch.object(score, "request", side_effect=TimeoutError()) as network,
            ThreadPoolExecutor(max_workers=2) as executor,
        ):
            results = list(executor.map(lambda _: dispatch(), range(2)))
            self.assertEqual(network.call_count, 1)
            self.assertCountEqual(results, ["completed", "checkpoint_already_claimed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
