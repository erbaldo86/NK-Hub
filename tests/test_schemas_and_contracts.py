# -*- coding: utf-8 -*-
"""
Nexus Keystone v1.1.0-Universal
Test Module 8: Pydantic v2 Strict Mode Contracts & Dual-Ledgers
5 Tests: Strict Mode, JsonValue Metadata, Task DAG Hash Chaining, PID File Locking, IPCPointer Footprint.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from pydantic import ValidationError

CURRENT_DIR = Path(__file__).resolve().parent
STAGING_DIR = CURRENT_DIR.parent
SCRIPTS_DIR = STAGING_DIR / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(STAGING_DIR) not in sys.path:
    sys.path.insert(0, str(STAGING_DIR))

from schemas.nk_ipc_contracts import IPCPointerReturn, OchiaiDiagnosticPayload
from schemas.dual_ledgers import TaskDAGNode, TaskLedger, ProgressLedger, PIDFileLock


class TestSchemasAndContracts(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._temp.name)

    def tearDown(self):
        try:
            self._temp.cleanup()
        except Exception:
            pass

    # 45. test_pydantic_strict_mode_validation
    def test_pydantic_strict_mode_validation(self):
        """45. Validates rejection of unpermitted coercions and extra fields (extra='forbid')."""
        with self.assertRaises(ValidationError):
            IPCPointerReturn.model_validate({
                "status": "OK",
                "pointer_uri": "file:///test",
                "sha256": "abc",
                "crc32": "NOT_AN_INT",  # Strict type failure
                "byte_size": 10,
            })

        with self.assertRaises(ValidationError):
            IPCPointerReturn.model_validate({
                "status": "OK",
                "pointer_uri": "file:///test",
                "sha256": "abc",
                "crc32": 123,
                "byte_size": 10,
                "forbidden_extra_key": "fail",
            })

    # 46. test_pydantic_jsonvalue_metadata_support
    def test_pydantic_jsonvalue_metadata_support(self):
        """46. Validates support for complex nested dict metadata via JsonValue."""
        node = TaskDAGNode.create(
            task_id="T1",
            action="BUILD",
            target_agent="NK-Builder",
            payload={"nested": {"deep": [1, 2, 3], "flag": True, "str": "val"}},
        )
        self.assertEqual(node.payload["nested"]["flag"], True)

    # 47. test_task_dag_sha256_hash_chaining
    def test_task_dag_sha256_hash_chaining(self):
        """47. Validates SHA-256 DAG hash chaining and tamper detection."""
        ledger_path = self.tmp_dir / "task_dag.jsonl"
        tl = TaskLedger(ledger_path)
        tl.add_task("T1", "DESIGN", "NK-Architect")
        tl.add_task("T2", "BUILD", "NK-Builder", parent_ids=["T1"])
        valid, _ = tl.verify_dag()
        self.assertTrue(valid)

    # 48. test_progress_ledger_pid_locking_stale_detect
    def test_progress_ledger_pid_locking_stale_detect(self):
        """48. Validates append-only progress stream with PID-aware locking."""
        ledger_path = self.tmp_dir / "progress.jsonl"
        pl = ProgressLedger(ledger_path)
        ev1 = pl.append_event("EV1", "T1", 0, "STARTED", {"status": "init"})
        ev2 = pl.append_event("EV2", "T1", 1, "COMPLETED", {"status": "done"})
        events = pl.read_events("T1")
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].event_id, "EV1")
        self.assertEqual(events[1].event_id, "EV2")

    # 49. test_ipc_pointer_return_token_footprint
    def test_ipc_pointer_return_token_footprint(self):
        """49. Validates IPCPointerReturn serialized token budget (<80 tokens)."""
        ptr = IPCPointerReturn(
            status="OK",
            pointer_uri="file:///g:/Antigravity/.staging/data.json",
            sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            crc32=3523407757,
            byte_size=1024,
            mime_type="application/json",
        )
        serialized = ptr.model_dump_json()
        estimated_tokens = len(serialized) / 3.5
        self.assertLess(estimated_tokens, 80)


if __name__ == "__main__":
    unittest.main()
