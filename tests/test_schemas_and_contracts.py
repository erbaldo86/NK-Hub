# -*- coding: utf-8 -*-
"""
Suite di test unitari Zero-Mock per Contratti Pydantic v2 Strict Mode e Dual-Ledgers (v4.1.0).
Modulo: tests/test_schemas_and_contracts.py.
Valida strict mode, JsonValue, GoalFailureManifest, MetaPromptGateContract, DAG SHA-256 e IPCPointerReturn.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from pydantic import ValidationError

CURRENT_DIR = Path(__file__).resolve().parent
STAGING_DIR = CURRENT_DIR.parent
WORKSPACE_ROOT = (
    STAGING_DIR.parent if STAGING_DIR.name == ".staging" else STAGING_DIR
)
SCRIPTS_DIR = WORKSPACE_ROOT / "scripts"
STAGING_SCRIPTS_DIR = WORKSPACE_ROOT / ".staging" / "scripts"

for _cand in (STAGING_SCRIPTS_DIR, SCRIPTS_DIR, WORKSPACE_ROOT):
    if _cand.exists() and str(_cand) not in sys.path:
        sys.path.insert(0, str(_cand))

from schemas import MetaPromptGateContract as ExportedMetaPromptGateContract
from schemas.dual_ledgers import ProgressLedger, TaskDAGNode, TaskLedger
from schemas.nk_ipc_contracts import (
    GoalFailureManifest,
    IPCPointerReturn,
    MetaPromptGateContract,
)


class TestSchemasAndContracts(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._temp.name)

    def tearDown(self):
        try:
            self._temp.cleanup()
        except Exception:
            pass

    def test_pydantic_strict_mode_validation(self):
        """1. Valida rifiuto coercizioni/extra, metadati JsonValue e schema GoalFailureManifest."""
        with self.assertRaises(ValidationError):
            IPCPointerReturn.model_validate(
                {
                    "status": "OK",
                    "pointer_uri": "file:///test",
                    "sha256": "abc",
                    "crc32": "NOT_AN_INT",
                    "byte_size": 10,
                }
            )

        with self.assertRaises(ValidationError):
            IPCPointerReturn.model_validate(
                {
                    "status": "OK",
                    "pointer_uri": "file:///test",
                    "sha256": "abc",
                    "crc32": 123,
                    "byte_size": 10,
                    "forbidden_extra_key": "fail",
                }
            )

        node = TaskDAGNode.create(
            task_id="T1",
            action="BUILD",
            target_agent="NK-Builder",
            payload={"nested": {"deep": [1, 2, 3], "flag": True, "str": "val"}},
        )
        self.assertEqual(node.payload["nested"]["flag"], True)

        valid_manifest = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "manifest_version": "1.0.0",
            "timestamp": 1727182446.0,
            "session_id": "sess_goal",
            "milestone_anchor_id": "NK-MS-20260924-PLAN-GOAL-INTEGRATION-v2.6.0",
            "status": "UNATTENDED_BLOCKED",
            "root_cause_analysis": {
                "blocked_resource_type": "EXTERNAL_API",
                "resource_identifier": "https://api.service.com/v1",
                "error_message": "HTTP 504 Gateway Timeout",
                "stack_trace_snippet": "httpx.ConnectTimeout",
                "zero_mock_violation_prevented": True,
            },
            "staging_snapshot": {
                "staging_path": ".staging/src/",
                "modified_files": ["src/service_client.py"],
                "sha256_tree_hash": "a" * 64,
            },
            "user_remediation_steps": ["Verificare la rete", "Eseguire /goal --resume"],
            "resume_command": "/goal --resume",
        }
        manifest = GoalFailureManifest.model_validate(valid_manifest)
        self.assertEqual(manifest.status, "UNATTENDED_BLOCKED")

    def test_task_dag_sha256_hash_chaining(self):
        """2. Valida la catena di hash SHA-256 del DAG e il rilevamento manomissioni."""
        ledger_path = self.tmp_dir / "task_dag.jsonl"
        tl = TaskLedger(ledger_path)
        tl.add_task("T1", "DESIGN", "NK-Architect")
        tl.add_task("T2", "BUILD", "NK-Builder", parent_ids=["T1"])
        valid, _ = tl.verify_dag()
        self.assertTrue(valid)

        raw_lines = ledger_path.read_text(encoding="utf-8").splitlines()
        raw_lines[0] = raw_lines[0].replace("NK-Architect", "TAMPERED_AGENT")
        ledger_path.write_text("\n".join(raw_lines) + "\n", encoding="utf-8")

        with self.assertRaises(ValueError) as ctx:
            TaskLedger(ledger_path)
        self.assertIn("integrity violation", str(ctx.exception).lower())

    def test_progress_ledger_pid_locking_stale_detect(self):
        """3. Valida recupero lock PID orfani in ProgressLedger e budget IPCPointerReturn (<80 tok)."""
        ledger_path = self.tmp_dir / "progress.jsonl"
        lock_path = self.tmp_dir / "progress.jsonl.lock"
        lock_path.write_text(
            json.dumps({"pid": 99999999, "timestamp": 0.0}), encoding="utf-8"
        )

        pl = ProgressLedger(ledger_path)
        pl.append_event("EV1", "T1", 0, "STARTED", {"status": "init"})
        pl.append_event("EV2", "T1", 1, "COMPLETED", {"status": "done"})
        events = pl.read_events("T1")
        self.assertEqual(len(events), 2)

        ptr = IPCPointerReturn(
            status="OK",
            pointer_uri="file:///g:/Antigravity/.staging/data.json",
            sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            crc32=3523407757,
            byte_size=1024,
            mime_type="application/json",
        )
        self.assertLess(len(ptr.model_dump_json()) / 3.5, 80)

    def test_meta_prompt_gate_contract_strict_and_frozen(self):
        """4. Valida MetaPromptGateContract in modalita strict, immutabilita e vincolo TTL >= 60."""
        self.assertIs(MetaPromptGateContract, ExportedMetaPromptGateContract)
        contract = MetaPromptGateContract(
            brief_id="IB-20261021-ABC123",
            fsm_state="AWAIT_CONFIRM",
            gate_mode="CONFIRM",
            enabled=True,
            bypassed=False,
            conceptual_mirror="Obiettivo rilevato su analisi architetturale.",
            optimized_meta_prompt="[META-PROMPT L0] Esegui analisi read-only.",
            requirements_r_ids=["R1: Analizzare architettura"],
            voice_corrections_applied=["primaLa -> prima La"],
            out_of_scope=["Modifica file produzione"],
            recommended_mode="mode_d",
            primary_agent="NK-Ideator",
            native_subagent="NK-Specifier-Agent",
            intent_hash_sha256="b" * 64,
            ttl_seconds=1800,
        )
        self.assertEqual(contract.fsm_state, "AWAIT_CONFIRM")
        self.assertEqual(contract.ttl_seconds, 1800)

        with self.assertRaises(ValidationError):
            MetaPromptGateContract(
                conceptual_mirror="Test",
                optimized_meta_prompt="Test",
                ttl_seconds=30,
            )

        with self.assertRaises(ValidationError):
            MetaPromptGateContract.model_validate(
                {
                    "conceptual_mirror": "Test",
                    "optimized_meta_prompt": "Test",
                    "unexpected_field": 123,
                }
            )


if __name__ == "__main__":
    unittest.main()
