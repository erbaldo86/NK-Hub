# -*- coding: utf-8 -*-
"""
Suite di test unitari Zero-Mock per Contratti Pydantic v2 Strict Mode e Dual-Ledgers (v6.4.0-Carbon).
Modulo: tests/test_schemas_and_contracts.py.
Valida strict mode, JsonValue, GoalFailureManifest, MetaPromptGateContract, DAG SHA-256 e IPCPointerReturn.
"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest

from pydantic import ValidationError
import pytest

try:
    import conftest as _nk_conftest  # noqa: F401
except ImportError:
    import tests.conftest as _nk_conftest  # noqa: F401

pytestmark = pytest.mark.fast

from schemas import MetaPromptGateContract as ExportedMetaPromptGateContract  # noqa: E402
from schemas.dual_ledgers import PIDFileLock, ProgressLedger, TaskDAGNode, TaskLedger  # noqa: E402
from schemas.nk_ipc_contracts import (  # noqa: E402
    GoalFailureManifest,
    IPCPointerReturn,
    MetaPromptGateContract,
)


class TestSchemasAndContracts(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._temp.name)

    def tearDown(self):
        with contextlib.suppress(Exception):
            self._temp.cleanup()

    def test_pydantic_strict_contracts_and_manifest(self):
        """1. Valida strict mode, JsonValue, GoalFailureManifest, IPCPointerReturn (<80 tok) e MetaPromptGateContract."""
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

        ptr = IPCPointerReturn(
            status="OK",
            pointer_uri="file:///g:/Antigravity/.staging/data.json",
            sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            crc32=3523407757,
            byte_size=1024,
            mime_type="application/json",
        )
        self.assertLess(len(ptr.model_dump_json()) / 3.5, 80)

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
            MetaPromptGateContract(conceptual_mirror="Test", optimized_meta_prompt="Test", ttl_seconds=30)
        with self.assertRaises(ValidationError):
            MetaPromptGateContract.model_validate({"conceptual_mirror": "Test", "optimized_meta_prompt": "Test", "unexpected_field": 123})

    def test_dual_ledgers_dag_chaining_and_progress_lock(self):
        """2. Valida facciata lazy dual_ledgers, hash SHA-256 DAG, manomissioni e recupero lock PID."""
        dl_rt = _nk_conftest.load_script_by_relpath("dual_ledgers_rt", "scripts/schemas/dual_ledgers.py")
        dl_rt._ensure_scripts_overlay_paths()
        self.assertIn("PIDFileLock", dir(dl_rt))
        self.assertTrue(callable(dl_rt.ProgressLedger) and callable(ProgressLedger))
        with self.assertRaises(AttributeError):
            getattr(dl_rt, "nonexistent_dual_ledger_attr")

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

        prog_path = self.tmp_dir / "progress.jsonl"
        lock_path = self.tmp_dir / "progress.jsonl.lock"
        lock_path.write_text(json.dumps({"pid": 99999999, "timestamp": 0.0}), encoding="utf-8")
        pl = dl_rt.ProgressLedger(prog_path)
        pl.append_event("EV1", "T1", 0, "STARTED", {"status": "init"})
        pl.append_event("EV2", "T1", 1, "COMPLETED", {"status": "done"})
        self.assertEqual(len(pl.read_events("T1")), 2)

    def _run_concurrent_stale_contention(self) -> None:
        """Esegue contesa multi-thread su stale lock verificando convergenza a singolo proprietario."""
        race_lock = self.tmp_dir / "race_stale.lock"
        race_lock.write_text(json.dumps({"pid": 99999999, "nonce": "dead-owner", "timestamp": 1.0}), encoding="utf-8")
        state_guard = threading.Lock()
        active_owners, max_owners, completed, errors = 0, 0, 0, []

        def worker() -> None:
            nonlocal active_owners, max_owners, completed
            lk = PIDFileLock(race_lock, stale_timeout_sec=0.5)
            if not lk.acquire(timeout_sec=4.0):
                errors.append("acquire_timeout")
                return
            try:
                with state_guard:
                    active_owners += 1
                    max_owners = max(max_owners, active_owners)
                    completed += 1
                time.sleep(0)
                with state_guard:
                    active_owners -= 1
            finally:
                lk.release()

        threads = [threading.Thread(target=worker) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=6.0)
        self.assertEqual(errors, [])
        self.assertEqual(completed, 6)
        self.assertEqual(max_owners, 1)
        self.assertFalse(race_lock.exists())

    def test_pid_file_lock_orphan_preemption_and_concurrent_contention(self):
        """3. Regressione [P0-1]: orphan 0-byte/corrotti, release (pid, nonce) e contesa concorrente."""
        zero_lock = self.tmp_dir / "zero_orphan.lock"
        zero_lock.write_bytes(b"")
        old_ts = time.time() - 10.0
        os.utime(zero_lock, (old_ts, old_ts))
        lk_zero = PIDFileLock(zero_lock, stale_timeout_sec=1.0)
        self.assertTrue(lk_zero.acquire(timeout_sec=1.0))
        payload = json.loads(zero_lock.read_text(encoding="utf-8"))
        self.assertEqual(payload["pid"], os.getpid())
        self.assertTrue(isinstance(payload.get("nonce"), str) and len(payload["nonce"]) >= 16)
        lk_zero.release()
        self.assertFalse(zero_lock.exists())

        corrupt_lock = self.tmp_dir / "corrupt_orphan.lock"
        corrupt_lock.write_text("{broken_json", encoding="utf-8")
        os.utime(corrupt_lock, (old_ts, old_ts))
        lk_cor = PIDFileLock(corrupt_lock, stale_timeout_sec=1.0)
        self.assertTrue(lk_cor.acquire(timeout_sec=1.0))
        lk_cor.release()
        self.assertFalse(corrupt_lock.exists())

        preempt_lock = self.tmp_dir / "preempted.lock"
        lk_a = PIDFileLock(preempt_lock, stale_timeout_sec=0.05)
        self.assertTrue(lk_a.acquire(timeout_sec=1.0))
        preempt_lock.write_text(json.dumps({"pid": os.getpid(), "nonce": "preemptor-nonce-999", "timestamp": time.time() + 60.0}), encoding="utf-8")
        lk_a.release()
        self.assertFalse(lk_a.acquired)
        self.assertEqual(json.loads(preempt_lock.read_text(encoding="utf-8"))["nonce"], "preemptor-nonce-999")
        preempt_lock.unlink(missing_ok=True)
        self._run_concurrent_stale_contention()

    def test_epistemic_firewall_rules_wire_and_t12_contracts(self):
        """4. Copre branch mancanti di epistemic_firewall_rules.py su JSON strict, V2, T12 e intent."""
        from _internal.nk_common import epistemic_firewall_patterns as fp, epistemic_firewall_rules as fr

        for bad_json in ('{"a": 1, "a": 2}', '{"x": NaN}'):
            with self.assertRaises(ValueError):
                fr._strict_json_loads(bad_json)

        blks_t, unc_t, _ = fr.scan_fences_strict("~~~py\nx = 1\n~~~\n")
        self.assertFalse(unc_t)
        self.assertEqual(blks_t[0]["lang"], "py")
        _, unc_o, _ = fr.scan_fences_strict("```json\n{}\n")
        self.assertTrue(unc_o)

        base_v2 = {
            "schema_version": "2.0.0", "handoff_id": "HO-1",
            "manifest": {"timestamp": "2026-11-22T00:00:00Z", "handoff_type": "PASSIVE_STANDBY"},
            "state_sha256": "a" * 64, "external_live_calls_prohibited": True,
            "payload": {"handoff_mode": "PASSIVE_STANDBY", "ecosystem_repos": [{"repo_id": "NK_Hub"}], "transcript_raw_jsonl_included": False},
        }
        self.assertTrue(fr._validate_v2_structure(base_v2, "PASSIVE_STANDBY"))
        for bad_patch in (
            {"extra_bad": 1}, {"schema_version": "1.0"}, {"manifest": {}}, {"manifest": {"timestamp": "x"}},
            {"state_sha256": "short"}, {"payload": {"handoff_mode": "OTHER", "ecosystem_repos": [{}]}},
            {"payload": {"handoff_mode": "PASSIVE_STANDBY", "ecosystem_repos": []}},
            {"payload": {"handoff_mode": "PASSIVE_STANDBY", "ecosystem_repos": [{}], "transcript_raw_jsonl_included": True}},
        ):
            self.assertFalse(fr._validate_v2_structure({**base_v2, **bad_patch}, "PASSIVE_STANDBY"))
        self.assertTrue(fr._validate_v2_structure({**base_v2, "payload": {"handoff_mode": "ACTIVE_CONTINUATION", "ecosystem_repos": [{}], "failed_reasoning_included": False, "active_brief_id": "IB-20261122-ABC123", "requirements": ["R1"]}}, "ACTIVE_CONTINUATION"))
        self.assertFalse(fr._validate_v2_structure({**base_v2, "payload": {"handoff_mode": "ACTIVE_CONTINUATION", "ecosystem_repos": [{}], "failed_reasoning_included": False, "active_brief_id": "BAD", "requirements": []}}, "ACTIVE_CONTINUATION"))
        self.assertTrue(fr._validate_v2_structure({**base_v2, "payload": {"handoff_mode": "CUSTOM", "ecosystem_repos": [{}]}}, "CUSTOM"))

        signed_v2 = dict(base_v2)
        signed_v2["envelope_sha256"] = fr.compute_envelope_sha256_stdlib(signed_v2)
        wire_ok = f"{fp.HANDOFF_V2_START_PASSIVE}\n# [NK-HANDOFF-V2] Mode: PASSIVE_STANDBY\n```json\n{json.dumps(signed_v2)}\n```\n{fp.HANDOFF_V2_END_PASSIVE}"
        self.assertIsNotNone(fr.parse_verified_handoff_v2_wire(wire_ok))
        for bad_w in ("", f"{fp.HANDOFF_V2_START_PASSIVE} bad", f"{fp.HANDOFF_V2_START_PASSIVE}\n# BAD\n```json\n{{}}\n```\n{fp.HANDOFF_V2_END_PASSIVE}", f"{fp.HANDOFF_V2_START_PASSIVE}\n```json\n{{bad\n```\n{fp.HANDOFF_V2_END_PASSIVE}"):
            self.assertIsNone(fr.parse_verified_handoff_v2_wire(bad_w))

        t12_jsonl = f"{fp.T12_HEADER_PREFIX}\nModalità: PASSIVE\n{fp.T12_START}\n### 1. Stato\n```json\n{{\"a\": 1}}\n{{\"b\": 2}}\n```\n{fp.T12_END}"
        self.assertTrue(fr.check_legacy_t12_framing(t12_jsonl)[0])
        self.assertTrue(fr.is_sealed_t12_json_capsule(t12_jsonl))
        self.assertEqual(fr.extract_t12_scan_lines(t12_jsonl)[1], [])
        for bad_t12, exp_err in (
            (f"{fp.T12_START}\n{fp.T12_END} extra", "T12_END_NOT_AT_EOF"),
            (f"x{fp.T12_START}\n{fp.T12_END}", "INVALID_T12_PREFIX"),
            (f"WRONG\n{fp.T12_START}\n{fp.T12_END}", "INVALID_T12_HEADER"),
            (f"{fp.T12_HEADER_PREFIX}\n`bad`\n{fp.T12_START}\n{fp.T12_END}", "INVALID_T12_MODE_LINE"),
            (f"{fp.T12_START}\n```json\n{fp.T12_END}", "UNCLOSED_FENCE"),
            (f"{fp.T12_START}\nno sec\n{fp.T12_END}", "MISSING_SECTION_1"),
        ):
            self.assertEqual(fr.check_legacy_t12_framing(bad_t12), (False, exp_err))

        self.assertIsNone(fr.detect_outbound_handoff_intent_fast("a\nb\nc"))
        self.assertIsNone(fr.detect_outbound_handoff_intent_fast("fammi handoff [NK-ANCHOR:x]"))
        self.assertIsNone(fr.detect_outbound_handoff_intent_fast("fammi handoff && rm -rf x"))
        self.assertEqual(fr.detect_outbound_handoff_intent_fast("Prepara un passive handoff"), "PASSIVE_STANDBY")
        self.assertEqual(fr.detect_outbound_handoff_intent_fast("Genera un active handoff di continuazione"), "ACTIVE_CONTINUATION")

    def test_handoff_verify_edge_branches(self):
        """5. Copre edge branch di handoff_verify.py: scope, scan, anchor tail e T12/V2 spoof."""
        _nk_conftest.load_nk_script_module("nk_session_bootstrap")
        from _internal.nk_common.epistemic_firewall_patterns import T12_END, T12_HEADER_PREFIX, T12_START
        from _internal.nk_session_bootstrap import handoff_verify as hv

        self.assertEqual([hv._sanitize_cid(x) for x in ("", "auto", "default_1", "conv-1")], ["", "", "", "conv-1"])
        ext_root = self.tmp_dir / "NK_External_Projects"
        allowed = ((self.tmp_dir / "NK_Hub").resolve(), (self.tmp_dir / "Proj").resolve(), ext_root.resolve())
        self.assertEqual([hv._is_repo_root_in_scope(p, allowed) for p in ((ext_root / "App1").resolve(), ext_root, self.tmp_dir / "outside")], [True, False, False])
        self.assertEqual(hv._scan_tracked_metadata(self.tmp_dir / "missing_repo"), {})

        ws = self.tmp_dir / "hv_ws"
        for d in (".git", "nk_tracking/sessions/cid-tail", "nk_tracking/handoff", "scripts"):
            (ws / d).mkdir(parents=True)
        (ws / ".git" / "HEAD").write_text("ref: main\n", encoding="utf-8")
        (ws / "nk_tracking" / "active_context.md").write_text("ctx\n", encoding="utf-8")
        (ws / "scripts" / "ok.py").write_text("X = 1\n", encoding="utf-8")
        meta = hv._scan_tracked_metadata(ws)
        self.assertIn("scripts/ok.py", meta)
        self.assertNotIn("nk_tracking/active_context.md", meta)
        self.assertNotIn(".git/HEAD", meta)

        sess_a = ws / "nk_tracking" / "sessions" / "cid-tail" / "session_anchor.jsonl"
        for raw, exp in ((b"", (None, False)), (b"[1, 2]\n", (None, True)), (b"{bad\n", (None, True)), (json.dumps({"conversation_id": "cid-tail"}).encode() + b"\n", ("cid-tail", False))):
            sess_a.write_bytes(raw)
            self.assertEqual(hv._inspect_anchor_tail(ws, "cid-tail"), exp)
        sigs, has_sha = hv._staging_sigs(["a\\b.py", {"rel_path": "c\\d.py", "sha256": "f" * 64}])
        self.assertTrue(has_sha)
        self.assertIn(("a/b.py", ""), sigs)

        self.assertEqual(hv.verify_handoff_envelope_live(ws, ws, handoff_file=self.tmp_dir / "missing.md")["reason"], "HANDOFF_FILE_NOT_FOUND")
        self.assertEqual(hv.verify_handoff_envelope_live(ws, ws, prompt_text="   ")["reason"], "EMPTY_PROMPT_TEXT")
        self.assertEqual(hv.verify_handoff_envelope_live(ws, ws)["reason"], "EMPTY_OR_MISSING_HANDOFF")
        self.assertEqual(hv.verify_handoff_envelope_live(ws, ws, prompt_text="# [NK-HANDOFF-V2] spoof")["reason"], "INVALID_OR_SPOOFED_V2_ENVELOPE")
        self.assertEqual(hv.verify_handoff_envelope_live(ws, ws, prompt_text=f"{T12_HEADER_PREFIX}\n{T12_START}\n### 1. Stato\nSHA256: nothex\n{T12_END}\n")["reason"], "MALFORMED_SHA256")
        (ws / "nk_tracking" / "handoff" / "next_session_prompt.md").write_text(f"{T12_HEADER_PREFIX}\n{T12_START}\n### 1. Stato\n- Stato passivo: pronto.\n{T12_END}\n", encoding="utf-8")
        res_t12 = hv.verify_handoff_envelope_live(ws, ws)
        self.assertEqual((res_t12["status"], res_t12["handoff_format"], res_t12["source"]), ("HANDOFF_VERIFY_OK", "LEGACY_T12", "next_session_prompt"))


if __name__ == "__main__":
    unittest.main()
