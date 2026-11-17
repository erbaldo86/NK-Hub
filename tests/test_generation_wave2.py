# -*- coding: utf-8 -*-
"""
Suite Zero-Mock Wave 2 per NK Hub Generation 1.0.0-Generation.
Modulo: tests/test_generation_wave2.py.
Valida costanti SSOT, i 16 trigger ONBOARDING_TRIGGERS sui 4 gate e il profilo generation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

try:
    from conftest import (
        CONFTEST_VERSION,
        WORKSPACE_ROOT,
        call_script_main_captured,
        load_nk_script_module,
        load_script_by_relpath,
    )
except ImportError:
    from tests.conftest import (
        CONFTEST_VERSION,
        WORKSPACE_ROOT,
        call_script_main_captured,
        load_nk_script_module,
        load_script_by_relpath,
    )


def _make_clean_ws(root: Path, name: str = "wave2_ws") -> Path:
    """Crea un workspace NK_Hub minimale isolato sotto root."""
    ws = root / name
    for sub in ("nk_tracking", ".wal", "scripts", ".agents"):
        (ws / sub).mkdir(parents=True, exist_ok=True)
    (ws / "nk_tracking" / "quality_baseline.json").write_text(
        json.dumps({"metrics": {"unit_tests_pass_pct": 100.0, "unit_tests_total": 100}}),
        encoding="utf-8",
    )
    return ws


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    """Scrive una lista di record JSONL UTF-8."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=True) + "\n" for r in rows),
        encoding="utf-8",
    )


_GEN_TRIGGERS: tuple[str, ...] = (
    "avvia generation",
    "avvia nk generation",
    "avvia nk hub generation",
    "avvia ambiente generation",
    "start generation",
    "start nk generation",
    "attiva generation",
    "attiva ambiente generation",
)


@pytest.mark.fast
def test_wave2_ssot_constants_and_thresholds_parity(tmp_path: Path) -> None:
    """Verifica VERSION, milestone, profili, 16 trigger SSOT e simmetria thresholds."""
    consts = load_script_by_relpath(
        "nk_common_constants_w2", "scripts/_internal/nk_common/constants.py"
    )
    thr = load_script_by_relpath(
        "nk_common_thresholds_w2", "scripts/_internal/nk_common/thresholds.py"
    )

    assert CONFTEST_VERSION == "1.0.0-Generation"
    assert consts.VERSION == "1.0.0-Generation"
    assert consts.DEFAULT_MILESTONE_ID == "NK-GEN-1.0.0"
    assert consts.SUPPORTED_MODEL_PROFILES == ("generation", "carbon", "argon", "standard")
    assert consts.HIGH_CAPACITY_PROFILES == ("generation", "carbon", "argon")
    assert len(consts.LEGACY_ONBOARDING_TRIGGERS) == 8
    assert consts.GENERATION_ONBOARDING_TRIGGERS == _GEN_TRIGGERS
    assert len(consts.ONBOARDING_TRIGGERS) == 16

    thr.clear_thresholds_cache()
    live_cfg = thr.load_saturation_thresholds(workspace_root=WORKSPACE_ROOT)
    gen_prof = live_cfg["profiles"]["generation"]
    carb_prof = live_cfg["profiles"]["carbon"]
    assert gen_prof["context_sentry"] == carb_prof["context_sentry"]
    assert gen_prof["runtime_sentinel"] == carb_prof["runtime_sentinel"]
    assert gen_prof["tier1_token_cap"] == 1200

    carb_only = tmp_path / "carb_only.json"
    carb_only.write_text(
        json.dumps({"profiles": {"carbon": {"runtime_sentinel": {"green_max_steps": 120}}}}),
        encoding="utf-8",
    )
    loaded_c = thr.load_saturation_thresholds(thresholds_path=carb_only)
    assert loaded_c["profiles"]["generation"]["runtime_sentinel"]["green_max_steps"] == 120

    gen_only = tmp_path / "gen_only.json"
    gen_only.write_text(
        json.dumps({"profiles": {"generation": {"runtime_sentinel": {"green_max_steps": 120}}}}),
        encoding="utf-8",
    )
    loaded_g = thr.load_saturation_thresholds(thresholds_path=gen_only)
    assert loaded_g["profiles"]["carbon"]["runtime_sentinel"]["green_max_steps"] == 120


@pytest.mark.fast
@pytest.mark.parametrize("trigger", _GEN_TRIGGERS)
def test_wave2_generation_triggers_across_4_gates(
    trigger: str, tmp_path: Path, isolated_nk_env: Path
) -> None:
    """Verifica gli 8 trigger Generation sui 4 gate (bootstrap, router, fastguard, compliance)."""
    assert isolated_nk_env.is_dir()
    boot_mod = load_nk_script_module("nk_session_bootstrap")
    router_mod = load_nk_script_module("vibe_sprint_router")
    fg_mod = load_nk_script_module("nk_acs_fastguard")
    comp_mod = load_nk_script_module("nk_compliance_checker")

    ws = _make_clean_ws(tmp_path, "gate_ws")
    (ws / ".wal" / "hold.wal").write_text('{"state":"PREPARED"}', encoding="utf-8")
    prompt_variant = f"{trigger.title()}!"

    boot = boot_mod.NKSessionBootstrap(
        workspace_root=ws, conversation_id="conv-gen-trig", prompt=prompt_variant
    )
    boot_res = boot.run_bootstrap(fast_stat=False)
    assert boot_res["onboarding_bypass"] == "ONBOARDING_BYPASS_VERIFIED"
    assert boot_res["checks"]["meta_prompt_gate"]["mode"] == "BYPASSED"

    router = router_mod.VibeSprintRouter(workspace_root=ws)
    assert router.is_gate_exempt(prompt_variant) is True
    assert router.evaluate_meta_prompt_gate(prompt_variant)["fsm_state"] == "BYPASSED"

    assert fg_mod._is_l0_exempt_fast(prompt_variant) is True
    tp = tmp_path / "tp_trig.jsonl"
    _write_jsonl(
        tp,
        [
            {
                "step_index": 1,
                "source": "USER_EXPLICIT",
                "type": "USER_INPUT",
                "content": f"<USER_REQUEST>\n{prompt_variant}\n</USER_REQUEST>",
            },
            {"step_index": 2, "source": "MODEL", "type": "PLANNER_RESPONSE", "input_tokens": 15_000, "content": "d"},
            {"step_index": 3, "source": "MODEL", "type": "PLANNER_RESPONSE", "input_tokens": 16_000, "content": "d"},
            {"step_index": 4, "source": "MODEL", "type": "PLANNER_RESPONSE", "input_tokens": 17_000, "content": "d"},
        ],
    )
    fg_stdin = json.dumps(
        {"conversationId": "conv-fg-gen", "projectRoot": str(ws), "transcriptPath": str(tp)}
    )
    rc_fg, out_fg, _ = call_script_main_captured(
        fg_mod, ["--event", "PreInvocation", "--native-contract"], stdin_text=fg_stdin
    )
    assert rc_fg == 0 and json.loads(out_fg) == {}

    checker = comp_mod.NKComplianceChecker(workspace_root=ws)
    comp_res = checker.audit_transcript(tp)
    assert comp_res["metrics"]["meta_prompt_gate_executed"] is False
    assert comp_res["scores"]["procedural_score"] == 100
    assert not any("Meta-Prompt Gate L0 omitted" in p for p in comp_res["penalties"])


@pytest.mark.fast
def test_wave2_analytical_generation_prompt_not_exempt(
    tmp_path: Path, isolated_nk_env: Path
) -> None:
    """Verifica che un prompt analitico contenente il trigger non attivi l'esenzione L0."""
    assert isolated_nk_env.is_dir()
    boot_mod = load_nk_script_module("nk_session_bootstrap")
    router_mod = load_nk_script_module("vibe_sprint_router")
    fg_mod = load_nk_script_module("nk_acs_fastguard")

    ws = _make_clean_ws(tmp_path, "neg_ws")
    analytical = "Analizza perche avvia generation fallisce nel log"
    assert router_mod.VibeSprintRouter(workspace_root=ws).is_gate_exempt(analytical) is False
    assert fg_mod._is_l0_exempt_fast(analytical) is False
    res = boot_mod.NKSessionBootstrap(
        workspace_root=ws, conversation_id="conv-neg-gen", prompt=analytical
    ).run_bootstrap(fast_stat=False)
    assert res["onboarding_bypass"] == "NONE"


@pytest.mark.fast
def test_wave2_generation_profile_runtime_parity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_nk_env: Path
) -> None:
    """Verifica NK_MODEL_PROFILE=generation su bootstrap, sentinel, sentry, mapper, hook, compliance, memory e handoff."""
    assert isolated_nk_env.is_dir()
    boot_mod = load_nk_script_module("nk_session_bootstrap")
    sent_mod = load_nk_script_module("nk_active_runtime_sentinel")
    cs_mod = load_nk_script_module("nk_context_sentry")
    map_mod = load_nk_script_module("ast_repo_mapper")
    hook_mod = load_nk_script_module("nk_hook_gate")
    comp_mod = load_nk_script_module("nk_compliance_checker")
    mem_mod = load_nk_script_module("memory_3tier_engine")
    hand_mod = load_nk_script_module("nk_session_handoff")

    ws = _make_clean_ws(tmp_path, "runtime_ws")
    monkeypatch.delenv("NK_MODEL_PROFILE", raising=False)
    assert boot_mod.NKSessionBootstrap(workspace_root=ws, conversation_id="conv-boot-unset").model_profile == "generation"
    rc_hu, out_hu, _ = call_script_main_captured(
        hook_mod,
        ["session-start", "--event", "SessionStart", "--conversation-id", "conv-hk-unset", "--project-root", str(ws)],
    )
    assert rc_hu == 0 and json.loads(out_hu)["profile"] == "generation"

    monkeypatch.setenv("NK_MODEL_PROFILE", "generation")

    boot_def = boot_mod.NKSessionBootstrap(workspace_root=ws, conversation_id="conv-boot-gen")
    assert boot_def.model_profile == "generation"
    tp_140 = tmp_path / "tp_140.jsonl"
    _write_jsonl(tp_140, [{"step_index": i, "source": "MODEL", "input_tokens": 100_000} for i in range(140)])
    boot_tp = boot_mod.NKSessionBootstrap(
        workspace_root=ws, conversation_id="conv-boot-140", transcript_path=tp_140
    )
    assert boot_tp.run_bootstrap(fast_stat=False)["checks"]["context_sentry"]["status"] == "GREEN"

    assert sent_mod.calculate_state(119, profile="generation") == "GREEN"
    assert sent_mod.calculate_state(120, profile="generation") == "CAUTION"
    assert sent_mod.calculate_state(180, profile="generation") == "CRITICAL"
    assert sent_mod.calculate_state(250, profile="generation") == "RED"
    assert sent_mod.calculate_state(2, profile="generation", actual_tokens=200_000) == "RED"
    tp_low = tmp_path / "tp_low.jsonl"
    _write_jsonl(tp_low, [{"step_index": 1, "source": "MODEL", "input_tokens": 12_000}])
    with monkeypatch.context() as mp_sent:
        mp_sent.setenv("NK_CONVERSATION_ID", "conv-sent-gen")
        rc_s, out_s, _ = call_script_main_captured(
            sent_mod, ["--transcript", str(tp_low), "--conversation-id", "conv-sent-gen", "--json"]
        )
    assert rc_s == 0 and json.loads(out_s)["profile"] == "generation"

    sentry = cs_mod.NKContextSentry(workspace_root=ws)
    assert sentry.profile == "generation"
    assert sentry.GENERATION_GREEN_STEP_THRESHOLD == 150
    assert sentry.GENERATION_RED_STEP_THRESHOLD == 250
    assert sentry.get_traffic_light_status(140, 120_000, actual_context_tokens=140_000)["status"] == "GREEN"
    assert sentry.get_traffic_light_status(160, 120_000, actual_context_tokens=140_000)["status"] == "YELLOW"
    assert sentry.get_traffic_light_status(40, 40_000, actual_context_tokens=160_000)["status"] == "WARN"
    assert sentry.get_traffic_light_status(40, 40_000, actual_context_tokens=205_000)["status"] == "RED"

    assert map_mod.CACHE_SCHEMA_VERSION == "1.0.0-Generation"
    assert map_mod.GraduatedSkillAdapter.get_token_budget("NK-Ideator", "generation_mode_c") == 512
    assert map_mod.GraduatedSkillAdapter.get_token_budget("NK-Ideator", "generation_mode_b") == 1500
    assert map_mod.GraduatedSkillAdapter.get_token_budget("NK-Ideator", "generation_mode_a") == 4000

    rc_hk, out_hk, _ = call_script_main_captured(
        hook_mod,
        ["session-start", "--event", "SessionStart", "--conversation-id", "conv-hk-gen", "--project-root", str(ws)],
    )
    assert rc_hk == 0 and json.loads(out_hk)["profile"] == "generation"
    rc_hkn, out_hkn, _ = call_script_main_captured(
        hook_mod,
        ["session-start", "--event", "SessionStart", "--native-contract", "--conversation-id", "conv-hkn", "--project-root", str(ws)],
    )
    assert rc_hkn == 0 and "Generation profile active" in out_hkn

    checker = comp_mod.NKComplianceChecker(workspace_root=ws)
    tp_warn = tmp_path / "tp_warn.jsonl"
    _write_jsonl(tp_warn, [{"step_index": 1, "source": "USER_EXPLICIT", "content": "Audit"}, {"step_index": 2, "source": "MODEL", "input_tokens": 160_000}])
    res_w = checker.audit_transcript(tp_warn)
    assert res_w["warn_advisory"] is True and res_w["scores"]["procedural_score"] == 100

    assert mem_mod.MEMORY_SCHEMA_VERSION == "1.0.0-Generation"
    assert mem_mod.TIER1_TOKEN_CAP_GENERATION == 1200
    assert mem_mod.Tier1CoreMemory(profile="generation").token_cap == 1200
    assert mem_mod.sync_tier1_capsule(base_dir=tmp_path / "m3_gen", profile="generation")["profile"] == "generation"

    assert hand_mod.HANDOFF_VERSION == "1.0.0-Generation"
    assert hand_mod.DEFAULT_MILESTONE_ID == "NK-GEN-1.0.0"
    ctx_view = hand_mod.generate_active_context_view(root=ws, profile="generation", dry_run=True)
    assert ctx_view["profile"] == "generation" and ctx_view["max_tokens"] == 1200
    assert "# Contesto Operativo Attivo NK Hub Generation" in ctx_view["content"]
