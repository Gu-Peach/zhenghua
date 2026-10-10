from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_service.infrastructure.document import checkpoint as wiring_graph


class AtomicCheckpointTests(unittest.TestCase):
    def test_json_checkpoint_retries_temporary_windows_replace_denial(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "checkpoint.json"
            real_replace = os.replace
            attempts = 0

            def replace_with_one_transient_failure(source: str, target: str) -> None:
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    raise PermissionError("simulated transient Windows file lock")
                real_replace(source, target)

            with (
                patch.object(os, "replace", side_effect=replace_with_one_transient_failure),
                patch.object(wiring_graph.time, "sleep"),
            ):
                wiring_graph._write_json_atomic(path, {"completed": [1]})

            self.assertEqual(attempts, 2)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"completed": [1]})
            self.assertEqual(list(Path(temporary).glob(".checkpoint.json.*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
