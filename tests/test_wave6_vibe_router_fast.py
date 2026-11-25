# -*- coding: utf-8 -*-
"""Test rapidi Wave 6 per vibe_sprint_router (intent, envelope, renderer e STT)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pytest

try:
    from conftest import load_nk_script_module
except ImportError:
    from tests.conftest import load_nk_script_module

pytestmark = pytest.mark.fast

router_mod = load_nk_script_module("vibe_sprint_router")
VibeSprintRouter = router_mod.VibeSprintRouter

from _internal.vibe_sprint_router import (  # noqa: E402
    envelope_builder,
    envelope_renderers,
    intent_builders,
    intent_classifier,
    stt_helpers,
    stt_normalize,
)


@pytest.mark.fast
def test_mode_d_discovery_candidate_boundaries() -> None:
    """Verifica confini phase_count, changed_lines ed explicit_mode per Mode D."""
    base: Dict[str, Any] = {
        "matched": ["x"],
        "has_negated_write": False,
        "has_gov_ro_verb": False,
        "has_code_files": False,
        "has_write_intent": False,
        "phase_count": 1,
        "changed_lines": None,
        "explicit_mode": None,
    }
    fn = intent_classifier._is_mode_d_discovery_candidate
    assert fn(**base) is True
    assert fn(**{**base, "phase_count": 2}) is False
    assert fn(**{**base, "phase_count": 3}) is False
    assert fn(**{**base, "changed_lines": 0}) is True
    assert fn(**{**base, "changed_lines": 5}) is False
    assert fn(**{**base, "explicit_mode": "mode_d"}) is True
    for blocking_mode in ("mode_a", "mode_b", "mode_c"):
        assert fn(**{**base, "explicit_mode": blocking_mode}) is False


@pytest.mark.fast
def test_normalize_gov_ro_domain_or_conditions() -> None:
    """Verifica le 4 condizioni OR indipendenti verso DOM-04 e il fallback invariato."""
    expected_dom04 = (
        "NK-Oracle-Evaluator",
        ["NK-Oracle-Evaluator", "NK-Agent-Instruction-Forge"],
        "NK-RSI-Auditor",
        "DOM-04",
        "AUDIT_DAST_AND_RCA",
    )
    dom_docs = {"domain_id": "DOM-05", "domain_name": "DOCS"}
    dom_build = {"domain_id": "DOM-03", "domain_name": "BUILD"}
    fn = intent_builders._normalize_gov_ro_domain

    assert fn(True, True, False, "NK-Scribe-Memory", ["NK-Scribe-Memory"], "NK-Scribe-Agent", dom_docs) == expected_dom04
    assert fn(True, False, False, "NK-Scribe-Memory", ["NK-Scribe-Memory"], "NK-Builder-Agent", dom_docs) == expected_dom04
    assert fn(True, False, False, "NK-Scribe-Memory", ["NK-Scribe-Memory"], "NK-RSI-Auditor", dom_docs) == expected_dom04
    assert fn(True, False, False, "NK-Scribe-Memory", ["NK-Scribe-Memory"], "NK-Scribe-Agent", dom_build) == expected_dom04
    assert fn(True, False, False, "NK-Agent-Instruction-Forge", ["NK-Agent-Instruction-Forge"], "NK-Scribe-Agent", dom_docs) == expected_dom04
    assert fn(True, False, False, "NK-Scribe-Memory", ["NK-Scribe-Memory"], "NK-Scribe-Agent", dom_docs) == (
        "NK-Scribe-Memory",
        ["NK-Scribe-Memory"],
        "NK-Scribe-Agent",
        "DOM-05",
        "DOCS",
    )


@pytest.mark.fast
def test_envelope_builder_tools_allowed_and_bypass_scope(tmp_path: Path) -> None:
    """Verifica tools_allowed in _resolve_standard_gate_state e 4 stati bypass_scope."""
    router = VibeSprintRouter(workspace_root=tmp_path)
    stt_stub = {"bypass_requested": False, "voice_corrections_applied": []}

    res_with_tools = envelope_builder._resolve_standard_gate_state(
        router, "spiega modulo", "spiega modulo", stt_stub, True, "CONFIRM", False,
        "mode_d", "mode_d", {"tools_allowed": ["read_file"], "recommended_mode": "mode_d"},
        "spiega modulo", None, None,
    )
    res_none_tools = envelope_builder._resolve_standard_gate_state(
        router, "spiega modulo", "spiega modulo", stt_stub, True, "CONFIRM", False,
        "mode_d", "mode_d", {"tools_allowed": None, "recommended_mode": "mode_d"},
        "spiega modulo", None, None,
    )
    assert res_with_tools[5] == ["read_file"]
    assert res_none_tools[5] == []

    base_state: Dict[str, Any] = {
        "requirements_r_ids": ["R1: Verifica stato"],
        "optimized_meta_prompt": "[META-PROMPT L0]",
        "auto_bypass_eligible": False,
        "conceptual_mirror": "Specchio L0",
        "out_of_scope": [],
        "role_conflicts": [],
        "rec_mode": "mode_d",
        "primary_ag": "NK-Ideator",
        "native_sub": "NK-Arch-Specifier",
        "tools_allowed": ["read_file"],
        "intrinsic_protocols": [],
        "slash_equivalence": {"goal": False, "boost": False, "plan": False, "implementation": False},
    }
    cases = (
        ("EXECUTE_HANDOFF_SERIALIZE", False, True, "BYPASSED", "EXECUTE_HANDOFF_SERIALIZE"),
        ("OTHER", False, True, "AWAIT_CONFIRM", "L0_GATE_ONLY"),
        (None, False, False, "BYPASSED", "L0_GATE_ONLY"),
        (None, False, False, "AWAIT_CONFIRM", "NONE"),
    )
    for reason, standby, bypassed, fsm_state, expected_scope in cases:
        state = {**base_state, "bypass_reason": reason, "standby_mode": standby, "bypassed": bypassed, "fsm_state": fsm_state}
        finalized = envelope_builder._finalize_envelope_result(router, state, stt_stub, True, "CONFIRM", False)
        assert finalized["bypass_scope"] == expected_scope


@pytest.mark.fast
def test_envelope_renderers_clause_split_and_active_v2() -> None:
    """Verifica soglie 2 vs 3 di _split_requirement_clauses e fallback _extract_active_v2_requirements."""
    split_fn = envelope_renderers._split_requirement_clauses
    assert split_fn("ab; cde; fg; hij") == ["cde", "hij"]
    assert split_fn("xy R1: alfa R2: beta") == ["R1: alfa", "R2: beta"]
    assert split_fn("xyz R1: alfa R2: beta") == ["xyz", "R1: alfa", "R2: beta"]
    assert split_fn("") == ["Eseguire il task richiesto"]
    assert split_fn("ok") == ["ok"]

    ext_fn = envelope_renderers._extract_active_v2_requirements
    assert ext_fn({"payload": {}, "requirements": ["Top req"]}) == ["R1: Top req"]
    assert ext_fn({"payload": {"requirements": ["Inner req"]}}) == ["R1: Inner req"]
    assert ext_fn({"last_summary": "Riprendi task"}) == ["R1: Riprendi task"]
    assert ext_fn({"payload": {"active_brief_id": "IB-20261123-AAAAAA"}}) == ["R1: IB-20261123-AAAAAA"]
    fallback_res = ext_fn({"payload": {"task_summary": "Riprendi task"}})
    assert isinstance(fallback_res, list) and fallback_res == ["R1: Eseguire la continuazione richiesta"]


@pytest.mark.fast
def test_stt_normalize_active_handoff_and_intrinsic_protocols(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica detect_active_continuation_handoff_impl e resolve_intrinsic_vibe_protocols_impl."""
    active_payload = {"payload": {"handoff_mode": "ACTIVE_CONTINUATION"}}
    top_mode_payload = {"payload": {}, "mode": "ACTIVE_CONTINUATION"}
    passive_payload = {"payload": {"handoff_mode": "PASSIVE_STANDBY"}}

    with monkeypatch.context() as mp:
        mp.setattr(stt_normalize, "parse_verified_handoff_v2_wire", lambda _t: active_payload)
        assert stt_normalize.detect_active_continuation_handoff_impl("   ") is None
        assert stt_normalize.detect_active_continuation_handoff_impl("handoff wire") == active_payload
        mp.setattr(stt_normalize, "parse_verified_handoff_v2_wire", lambda _t: top_mode_payload)
        assert stt_normalize.detect_active_continuation_handoff_impl("handoff wire") == top_mode_payload
        mp.setattr(stt_normalize, "parse_verified_handoff_v2_wire", lambda _t: passive_payload)
        assert stt_normalize.detect_active_continuation_handoff_impl("handoff wire") is None

    router = VibeSprintRouter(workspace_root=tmp_path)
    with monkeypatch.context() as mp:
        mp.setattr(stt_normalize, "is_passive_state_handoff_impl", lambda _r, _t: True)
        mp.setattr(stt_normalize, "detect_outbound_handoff_intent_impl", lambda _t: None)
        res_passive = stt_normalize.resolve_intrinsic_vibe_protocols_impl(router, "testo")
        assert res_passive["recommended_mode"] == "mode_d" and res_passive["intrinsic_protocols"] == []

        mp.setattr(stt_normalize, "is_passive_state_handoff_impl", lambda _r, _t: False)
        mp.setattr(stt_normalize, "detect_outbound_handoff_intent_impl", lambda _t: "PASSIVE_STANDBY")
        res_out = stt_normalize.resolve_intrinsic_vibe_protocols_impl(router, "testo")
        assert res_out["recommended_mode"] == "mode_d" and res_out["intrinsic_protocols"] == []

    res_a = stt_normalize.resolve_intrinsic_vibe_protocols_impl(router, "crea modulo", recommended_mode="mode_a")
    assert res_a["recommended_mode"] == "mode_a" and "INTRINSIC_BOOST" in res_a["intrinsic_protocols"]
    res_empty = stt_normalize.resolve_intrinsic_vibe_protocols_impl(router, "crea modulo", recommended_mode="")
    assert res_empty["recommended_mode"] == "mode_c"
    res_custom = stt_normalize.resolve_intrinsic_vibe_protocols_impl(router, "crea modulo", recommended_mode="custom_mode")
    assert res_custom["recommended_mode"] == "custom_mode"


@pytest.mark.fast
def test_stt_helpers_voice_corrections_and_bypass_toggle() -> None:
    """Verifica trigger token vocali in _apply_voice_corrections e toggle bypass espliciti."""
    noisy = "scusa, anzi, o meglio, volevo dire praticamente crea piano"
    corr_noisy: List[str] = []
    out_noisy = stt_helpers._apply_voice_corrections(noisy, corr_noisy)
    assert len(corr_noisy) >= 1 and out_noisy != noisy

    clean = "implementa modulo pulito"
    corr_clean: List[str] = []
    out_clean = stt_helpers._apply_voice_corrections(clean, corr_clean)
    assert out_clean == clean and corr_clean == []

    toggle = stt_helpers._check_explicit_bypass_toggle
    assert toggle("!diretto spiega", "!diretto spiega") is True
    assert toggle("!raw spiega", "!raw spiega") is True
    assert toggle("spiega", "spiega") is None
    assert toggle("!diretto modifica && rm", "!diretto modifica && rm") is False
