# -*- coding: utf-8 -*-
"""
Golden Test GT-NEW-01 v6.4.0-Carbon: Isolamento Sessione, Auto-Ancoraggio e Sicurezza test/.
Modulo: tests/test_session_isolation.py.
Zero mock/stub; valida resolve_session_tracking_dir, fastguard, hook_gate e PreflightHealthChecker.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

try:
    from conftest import (
        WORKSPACE_ROOT as _WORKSPACE_ROOT,
        load_script_by_relpath as _load_mod,
    )
except ImportError:
    from tests.conftest import (
        WORKSPACE_ROOT as _WORKSPACE_ROOT,
        load_script_by_relpath as _load_mod,
    )

pytestmark = pytest.mark.fast

hand_mod = _load_mod("nk_session_handoff", "scripts/nk_session_handoff.py")
acs_mod = _load_mod("nk_acs_fastguard", "scripts/nk_acs_fastguard.py")
hook_mod = _load_mod("nk_hook_gate", "scripts/nk_hook_gate.py")
pre_mod = _load_mod("preflight_health_check", "scripts/preflight_health_check.py")


def test_session_tracking_dir_validation_and_state_isolation(tmp_path: Path) -> None:
    """Verifica resolve_session_tracking_dir, blocco traversal, fallback default e isolamento hash/anchor."""
    ws = tmp_path / "iso_hub"
    (ws / "scripts").mkdir(parents=True)
    (ws / "nk_tracking").mkdir(parents=True)
    (ws / "scripts" / "core.py").write_text("VAL = 1\n", encoding="utf-8")

    valid_dir = hand_mod.resolve_session_tracking_dir(ws, "conv-alpha_01")
    expected_dir = (ws / "nk_tracking" / "sessions" / "conv-alpha_01").resolve()
    assert valid_dir == expected_dir

    dots = "." + "."
    invalid_ids = (
        None,
        "",
        "   ",
        "default_abc123",
        f"{dots}/escape",
        f"sess/{dots}/evil",
        "nested/sub",
        "nested\\sub",
        "bad$chars!",
        "x" * 65,
    )
    for bad_id in invalid_ids:
        assert hand_mod.resolve_session_tracking_dir(ws, bad_id) is None

    fb_a = acs_mod._resolve_conv_id(None, {}, str(ws / "repo_a"))
    fb_b = acs_mod._resolve_conv_id(None, {}, str(ws / "repo_b"))
    assert fb_a.startswith("default_") and fb_b.startswith("default_") and fb_a != fb_b
    assert acs_mod._resolve_conv_id("explicit_cid_9", {}, str(ws)) == "explicit_cid_9"

    cp_alpha = hand_mod.record_fsm_checkpoint(
        turn=2,
        gate_status="PASS",
        milestone_id="MS-ALPHA",
        root=ws,
        state_sha256_override="0" * 64,
        conversation_id="sess_alpha",
    )
    cp_beta = hand_mod.record_fsm_checkpoint(
        turn=4,
        gate_status="PASS",
        milestone_id="MS-BETA",
        root=ws,
        conversation_id="sess_beta",
    )
    assert Path(cp_alpha["session_anchor_path"]).is_file()
    assert Path(cp_beta["session_anchor_path"]).is_file()
    assert Path(cp_alpha["session_anchor_path"]) != Path(cp_beta["session_anchor_path"])

    res_alpha = hand_mod.resume_from_anchor(root=ws, conversation_id="sess_alpha")
    res_beta = hand_mod.resume_from_anchor(root=ws, conversation_id="sess_beta")
    assert res_alpha["passed"] is False and res_alpha["status"] == "DRIFT_DETECTED"
    assert res_alpha["milestone_id"] == "MS-ALPHA" and res_alpha["turn"] == 2
    assert res_beta["passed"] is True and res_beta["status"] == "RESUMED"
    assert res_beta["milestone_id"] == "MS-BETA" and res_beta["turn"] == 4
    assert res_beta["state_sha256"] == res_beta["expected_state_sha256"]


def test_parent_root_auto_anchoring_and_sibling_test_dir_safety(tmp_path: Path) -> None:
    """Verifica auto-ancoraggio Antigravity -> NK_Hub e incolumita di Antigravity/test/ sotto Preflight auto_fix."""
    fake_parent = tmp_path / "Antigravity"
    fake_sibling_test = fake_parent / "test"
    fake_sibling_test.mkdir(parents=True)
    keep_file = fake_sibling_test / "keep_artifact.txt"
    keep_file.write_text("SIBLING_TEST_INTACT", encoding="utf-8")

    fake_hub = fake_parent / "NK_Hub"
    (fake_hub / "scripts").mkdir(parents=True)
    (fake_hub / ".staging").mkdir(parents=True)
    (fake_hub / "nk_tracking" / "anchor").mkdir(parents=True)
    (fake_hub / "nk_genome" / "nk_registry_manifest.json").parent.mkdir(parents=True, exist_ok=True)
    (fake_hub / "nk_genome" / "nk_registry_manifest.json").write_text(
        '{"skills_index": {"NK-S1": {}}}', encoding="utf-8"
    )
    (fake_hub / "nk_tracking" / "quality_baseline.json").write_text(
        '{"metrics": {"skills_audited": 1, "crv_macro_phases": 4, "unit_tests_pass_pct": 100.0}}',
        encoding="utf-8",
    )

    eff_acs = acs_mod._resolve_eff_root({"cwd": str(fake_parent)}, str(fake_parent))
    eff_hook = hook_mod._resolve_effective_hub_root(fake_parent)
    assert eff_acs == os.path.realpath(str(fake_hub))
    assert eff_hook == fake_hub.resolve()

    rep_hub = pre_mod.PreflightHealthChecker(workspace_root=fake_hub).run_full_check(auto_fix=True)
    rep_parent = pre_mod.PreflightHealthChecker(workspace_root=fake_parent).run_full_check(auto_fix=True)
    assert rep_hub["status"] == "HEALTHY_GREEN"
    assert isinstance(rep_parent, dict)
    assert keep_file.exists() and keep_file.read_text(encoding="utf-8") == "SIBLING_TEST_INTACT"

    real_parent = _WORKSPACE_ROOT.parent
    real_sibling_test = real_parent / "test"
    if real_sibling_test.is_dir():
        real_snapshot = sorted(p.name for p in real_sibling_test.iterdir())
        assert hook_mod._resolve_effective_hub_root(real_parent) == _WORKSPACE_ROOT.resolve()
        assert acs_mod._resolve_eff_root({}, str(real_parent)) == os.path.realpath(str(_WORKSPACE_ROOT))
        assert sorted(p.name for p in real_sibling_test.iterdir()) == real_snapshot
